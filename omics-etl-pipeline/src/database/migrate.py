"""
Migração não-destrutiva do schema v1 → v2.

v1: fact_sinal tem compound_code UNIQUE global; candidato_sinal sem batch_id.
v2: fact_sinal tem UNIQUE(compound_code, batch_id); candidato_sinal tem batch_id.

Todos os dados existentes são preservados sob um batch sintético 'legado'.
A migração é idempotente: re-executar é seguro.
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
