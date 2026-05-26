"""
Migrações não-destrutivas do schema do banco de dados.

v1 → v2: fact_sinal ganha batch_id; candidato_sinal ganha batch_id.
          Dados existentes preservados sob batch sintético 'legado'.

v2 → v3: candidato_sinal ganha score_ranking e score_data_quality.
          score_ranking substitui score_total como critério de ordenação.
          score_data_quality indica completude de metadados (não entra no rank).
          Dados históricos recalculados inline; score_total/score_metadata
          mantidos como aliases de backward compatibility.

Todas as migrações são idempotentes: re-executar é seguro.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)

_HASH_LEGADO = "__legado_v1__"


def precisa_migrar(conn: sqlite3.Connection) -> bool:
    """Retorna True se fact_sinal existe mas ainda não tem coluna batch_id."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fact_sinal'")
    if not cur.fetchone():
        return False  # tabela não existe — banco fresh, nenhuma migração necessária
    cur.execute("PRAGMA table_info(fact_sinal)")
    colunas = {row[1] for row in cur.fetchall()}
    return "batch_id" not in colunas


def migrar_v1_para_v2(conn: sqlite3.Connection) -> None:
    """
    Executa a migração v1 → v2 dentro de uma transação.

    Passos:
        1. Cria batch sintético 'legado' em batch_execucao.
        2. Recria fact_sinal com batch_id (via CREATE + INSERT + DROP + RENAME).
        3. Adiciona batch_id em candidato_sinal via ALTER TABLE.
        4. Atualiza batch legado com as estatísticas dos dados migrados.
        5. Recria os índices que ficam inválidos após o RENAME.
    """
    if not precisa_migrar(conn):
        return

    logger.info("Iniciando migração v1 → v2 (adicionando batch_id nas tabelas ETL)...")
    cur = conn.cursor()

    # 1. Batch sintético para dados pré-migração
    cur.execute(
        """
        INSERT INTO batch_execucao
            (status, fonte, nome_ident, nome_abund, hash_ident, hash_abund)
        VALUES ('sucesso', 'legado', 'dados_pre_v2', 'dados_pre_v2', ?, ?)
        """,
        (_HASH_LEGADO, _HASH_LEGADO),
    )
    legado_id = cur.lastrowid
    logger.info(f"Batch legado criado: id={legado_id}")

    # 2. Recria fact_sinal com batch_id
    # FK enforcement desativado temporariamente para permitir DROP + RENAME
    conn.execute("PRAGMA foreign_keys = OFF")

    cur.execute("""
        CREATE TABLE fact_sinal_v2 (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id        INTEGER NOT NULL REFERENCES batch_execucao(id),
            compound_code   TEXT NOT NULL,
            mz              REAL NOT NULL,
            retention_time  REAL,
            abundancia      REAL,
            data_insercao   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(compound_code, batch_id)
        )
    """)

    cur.execute(
        f"""
        INSERT INTO fact_sinal_v2
            (id, batch_id, compound_code, mz, retention_time, abundancia, data_insercao)
        SELECT id, {legado_id}, compound_code, mz, retention_time, abundancia, data_insercao
        FROM fact_sinal
        """
    )

    # Dropa views que referenciam fact_sinal antes do RENAME
    # (SQLite valida views durante ALTER TABLE RENAME)
    cur.execute("DROP VIEW IF EXISTS vw_ranking_candidatos")
    cur.execute("DROP VIEW IF EXISTS vw_ranking_historico")

    cur.execute("DROP TABLE fact_sinal")
    cur.execute("ALTER TABLE fact_sinal_v2 RENAME TO fact_sinal")

    # 3. Adiciona batch_id em candidato_sinal
    try:
        cur.execute("ALTER TABLE candidato_sinal ADD COLUMN batch_id INTEGER")
    except sqlite3.OperationalError:
        pass  # coluna já existe (re-execução segura)
    cur.execute(f"UPDATE candidato_sinal SET batch_id = {legado_id}")

    conn.execute("PRAGMA foreign_keys = ON")

    # 4. Recria índices (ficam órfãos após DROP + RENAME)
    cur.execute("DROP INDEX IF EXISTS idx_compound_code")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_compound_code ON fact_sinal (compound_code)")
    cur.execute("DROP INDEX IF EXISTS idx_sinal_batch")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sinal_batch ON fact_sinal (batch_id)")
    cur.execute("DROP INDEX IF EXISTS idx_candidato_batch")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_candidato_batch ON candidato_sinal (batch_id)")

    # 5. Atualiza estatísticas do batch legado
    cur.execute("SELECT COUNT(DISTINCT compound_code) FROM fact_sinal WHERE batch_id = ?", (legado_id,))
    total_sinais = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM candidato_sinal WHERE batch_id = ?", (legado_id,))
    total_candidatos = cur.fetchone()[0]

    cur.execute(
        """
        UPDATE batch_execucao SET
            total_sinais     = ?,
            total_candidatos = ?,
            concluido_em     = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (total_sinais, total_candidatos, legado_id),
    )

    conn.commit()
    logger.info(
        f"Migração v1→v2 concluída: batch_id={legado_id} (legado), "
        f"{total_sinais} sinais, {total_candidatos} candidatos preservados."
    )


# ---------------------------------------------------------------------------
# Migração v2 → v3
# ---------------------------------------------------------------------------

def _precisa_migrar_v3(conn: sqlite3.Connection) -> bool:
    """Retorna True se candidato_sinal existe mas ainda não tem score_ranking."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidato_sinal'"
    )
    if not cur.fetchone():
        return False
    cur.execute("PRAGMA table_info(candidato_sinal)")
    return "score_ranking" not in {row[1] for row in cur.fetchall()}


def migrar_v2_para_v3(conn: sqlite3.Connection) -> None:
    """
    Migração v2 → v3: adiciona score_ranking e score_data_quality em
    candidato_sinal e recalcula os scores de todos os registros históricos.

    Passos:
        1. Adiciona colunas score_ranking e score_data_quality via ALTER TABLE.
        2. Lê todos os candidatos com seus dados de instrumento e de dim_molecula.
        3. Recalcula score_ranking (média ponderada) e score_data_quality
           (completude) para cada registro usando a mesma lógica de load.py.
        4. Atualiza score_total e score_metadata como aliases de backward compat.
        5. Recalcula rank_posicao usando score_ranking para todos os batches.

    A lógica de scoring está inlineada aqui para manter a migração
    auto-contida e independente de versões futuras de load.py.
    """
    if not _precisa_migrar_v3(conn):
        return

    logger.info("Iniciando migração v2 → v3 (adicionando score_ranking / score_data_quality)...")
    cur = conn.cursor()

    # 1. Adiciona colunas
    for coluna in ("score_ranking", "score_data_quality"):
        try:
            cur.execute(
                f"ALTER TABLE candidato_sinal ADD COLUMN {coluna} REAL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass  # já existe — re-execução segura

    # 2. Lê candidatos com dados necessários para o cálculo
    cur.execute("""
        SELECT
            c.id,
            c.score_fragmentacao,
            c.score_lab,
            c.score_isotopo,
            c.mass_error_ppm,
            c.neutral_mass_da,
            m.peso_molecular,
            m.formula,
            m.pubchem_cid,
            m.chebi_id,
            m.classe_quimica
        FROM candidato_sinal c
        JOIN dim_molecula m ON c.molecula_id = m.id
    """)
    registros = cur.fetchall()

    # 3 + 4. Recalcula e prepara updates
    # Lógica inlineada para independência de versões futuras de load.py
    _W = {"frag": 0.40, "lab": 0.30, "iso": 0.20, "massa": 0.10}
    _PPM_MAX  = 5.0
    _PPM_ZERO = 20.0
    _CAMPOS_DQ = ("formula", "pubchem_cid", "peso_molecular", "chebi_id", "classe_quimica")

    def _n01(v, mx):
        if v is None:
            return None
        try:
            f = float(v)
            return None if f != f else max(0.0, min(1.0, f / mx))  # nan check
        except (TypeError, ValueError):
            return None

    def _n_massa(mep, nm, pm):
        ppm = None
        if mep is not None:
            try:
                ppm = abs(float(mep))
            except (TypeError, ValueError):
                pass
        if ppm is None and nm is not None and pm is not None:
            try:
                n, t = float(nm), float(pm)
                if t > 0:
                    ppm = abs(n - t) / t * 1e6
            except (TypeError, ValueError):
                pass
        if ppm is None:
            return None
        if ppm <= _PPM_MAX:
            return 1.0
        if ppm >= _PPM_ZERO:
            return 0.0
        return 1.0 - (ppm - _PPM_MAX) / (_PPM_ZERO - _PPM_MAX)

    updates = []
    for (cid, sf, sl, si, mep, nm, pm, formula, pcid, chebi, classe) in registros:
        row = {
            "score_fragmentacao": sf, "score_lab": sl, "score_isotopo": si,
            "mass_error_ppm": mep, "neutral_mass_da": nm, "peso_molecular": pm,
            "formula": formula, "pubchem_cid": pcid, "chebi_id": chebi,
            "classe_quimica": classe,
        }

        componentes = [
            (_W["frag"],  _n01(sf,   100.0)),
            (_W["lab"],   _n01(sl,   100.0)),
            (_W["iso"],   _n01(si,   100.0)),
            (_W["massa"], _n_massa(mep, nm, pm)),
        ]
        validos = [(w, v) for w, v in componentes if v is not None]
        if validos:
            soma_w = sum(w for w, _ in validos)
            ranking = round(sum(w * v for w, v in validos) / soma_w * 100, 4)
        else:
            ranking = 0.0

        ok = sum(
            1 for campo in _CAMPOS_DQ
            if row.get(campo) is not None
            and str(row.get(campo)).strip() not in ("", "None", "Nao classificada")
        )
        quality = round(ok / len(_CAMPOS_DQ) * 100, 1)

        updates.append((ranking, quality, ranking, quality, cid))

    cur.executemany(
        """
        UPDATE candidato_sinal SET
            score_ranking      = ?,
            score_data_quality = ?,
            score_total        = ?,
            score_metadata     = ?
        WHERE id = ?
        """,
        updates,
    )

    # 5. Recalcula rank_posicao usando score_ranking para todos os batches
    cur.execute("SELECT DISTINCT batch_id FROM candidato_sinal")
    for (bid,) in cur.fetchall():
        cur.execute(
            """
            UPDATE candidato_sinal
            SET rank_posicao = (
                SELECT COUNT(*) + 1
                FROM candidato_sinal cs2
                WHERE cs2.sinal_id      = candidato_sinal.sinal_id
                  AND cs2.batch_id      = candidato_sinal.batch_id
                  AND cs2.score_ranking > candidato_sinal.score_ranking
            )
            WHERE batch_id = ?
            """,
            (bid,),
        )

    conn.commit()
    logger.info(
        f"Migração v2→v3 concluída: {len(updates)} candidatos com "
        "score_ranking recalculado."
    )


# ---------------------------------------------------------------------------
# Migração v3 → v4
# ---------------------------------------------------------------------------

def _precisa_migrar_v4(conn: sqlite3.Connection) -> bool:
    """Retorna True se candidato_sinal existe mas ainda não tem rank_group."""
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='candidato_sinal'"
    )
    if not cur.fetchone():
        return False
    cur.execute("PRAGMA table_info(candidato_sinal)")
    return "rank_group" not in {row[1] for row in cur.fetchall()}


def migrar_v3_para_v4(conn: sqlite3.Connection) -> None:
    """
    Migração v3 → v4: adiciona campos de ranking hierárquico IST em candidato_sinal
    e retroaplica o ranking para todos os batches existentes.

    Novas colunas:
        rank_group         — mesmo valor que rank_posicao (grupo explícito de empate)
        is_tied            — 0/1: True quando múltiplos candidatos dividem rank_posicao
        criterio_desempate — critério que resolveu (ou não) o empate
        ranking_metodo     — 'hierarquico_ist'

    rank_posicao existente é reescrito com o novo algoritmo hierárquico.
    score_ranking é preservado como campo diagnóstico/legado.

    Idempotente: seguro re-executar.
    """
    if not _precisa_migrar_v4(conn):
        return

    from src.etl.load import _atualizar_ranking_hierarquico

    logger.info("Migração v3→v4: adicionando campos de ranking hierárquico IST...")
    cur = conn.cursor()

    for col, defn in [
        ("rank_group",         "INTEGER"),
        ("is_tied",            "INTEGER DEFAULT 0"),
        ("criterio_desempate", "TEXT"),
        ("ranking_metodo",     "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE candidato_sinal ADD COLUMN {col} {defn}")
        except sqlite3.OperationalError:
            pass  # coluna já existe — re-execução segura

    conn.commit()

    cur.execute(
        "SELECT DISTINCT batch_id FROM candidato_sinal WHERE batch_id IS NOT NULL"
    )
    batch_ids = [row[0] for row in cur.fetchall()]

    for bid in batch_ids:
        _atualizar_ranking_hierarquico(cur, bid)

    conn.commit()
    logger.info(
        f"Migração v3→v4 concluída: {len(batch_ids)} batch(es) com "
        "ranking hierárquico IST aplicado."
    )
