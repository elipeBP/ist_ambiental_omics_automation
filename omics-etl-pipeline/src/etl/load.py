import sqlite3
import logging
import sys
from pathlib import Path
from typing import Tuple

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# score_massa_ppm — componente de erro de massa
#
# Thresholds baseados em boas práticas de HRMS (Q-TOF / Orbitrap).
# Instrumentos modernos de alta resolução operam tipicamente a 1–5 ppm.
# Calibráveis pelo IST conforme o equipamento utilizado.
# ---------------------------------------------------------------------------
TOLERANCIA_PPM_MAX  = 5.0   # ≤  5 ppm → score_massa = 40 (match excelente)
TOLERANCIA_PPM_ZERO = 20.0  # ≥ 20 ppm → score_massa = 0  (match descartado)

# ---------------------------------------------------------------------------
# score_ranking — pesos da média ponderada linear
#
# VALORES PROVISÓRIOS — devem ser calibrados pelo IST com base em resultados
# reais do instrumento e critérios de confiança da análise laboratorial.
#
# Fundamentação técnica:
#   W_FRAG  = 0.40 → fragmentação MS/MS: critério gold-standard em LC-MS/MS;
#                    único que distingue isômeros com mesma fórmula molecular.
#   W_LAB   = 0.30 → score geral do instrumento: integra heurísticas internas
#                    do software do equipamento (adducts, RT, etc.).
#   W_ISO   = 0.20 → similaridade isotópica: valida composição elementar;
#                    menos discriminativo que fragmentação para isômeros.
#   W_MASSA = 0.10 → erro de massa em ppm: tiebreaker — dados de HRMS já
#                    passam por filtro interno do instrumento, variação pequena.
#
# Referências: Schymanski et al. (2014) Environ. Sci. Technol. 48(4):2097–2098;
#              Sumner et al. (2007) Metabolomics 3(3):211–221.
# ---------------------------------------------------------------------------
W_FRAG  = 0.40
W_LAB   = 0.30
W_ISO   = 0.20
W_MASSA = 0.10

# Campos avaliados no score_data_quality (completude de metadados externos)
_CAMPOS_DATA_QUALITY = (
    "formula", "pubchem_cid", "peso_molecular", "chebi_id", "classe_quimica"
)

# ---------------------------------------------------------------------------
# Ranking hierárquico IST — critérios sequenciais de desempate
#
# Ordem de prioridade validada pelo IST:
#   1. score_fragmentacao  — maior é melhor; 0/None = sem poder discriminativo
#   2. score_lab           — maior é melhor; None = dado ausente
#   3. score_isotopo       — maior é melhor; None = dado ausente
#   4. mass_error_ppm      — menor valor absoluto é melhor; None = dado ausente
#   5. formula             — desempate alfabético determinístico
#   6. empate persistente  → decisão humana (is_tied=True)
# ---------------------------------------------------------------------------
_INF     = float('inf')
_NEG_INF = float('-inf')

_CRITERIO_NAMES = ('fragmentacao', 'score_lab', 'isotopo', 'massa', 'formula')


def _frag_key(v) -> float:
    """
    Chave de ordenação para fragmentation score.
    0 e None/NaN → _NEG_INF: sem poder discriminativo neste critério (vai para o fim).
    Valores positivos → valor bruto (quanto maior, melhor).
    """
    if v is None:
        return _NEG_INF
    try:
        f = float(v)
        if pd.isna(f) or f <= 0:
            return _NEG_INF
        return f
    except (TypeError, ValueError):
        return _NEG_INF


def _numeric_key_desc(v) -> float:
    """Chave descendente genérica (maior = melhor). None/NaN → _NEG_INF (vai para o fim)."""
    if v is None:
        return _NEG_INF
    try:
        f = float(v)
        return _NEG_INF if pd.isna(f) else f
    except (TypeError, ValueError):
        return _NEG_INF


def _mass_key_asc(v) -> float:
    """Chave para erro de massa: valor absoluto, ascendente (menor = melhor). None/NaN → +inf."""
    if v is None:
        return _INF
    try:
        f = float(v)
        return _INF if pd.isna(f) else abs(f)
    except (TypeError, ValueError):
        return _INF


def _formula_key_asc(v) -> str:
    """Chave de fórmula: string alfabética para desempate determinístico final. None → último."""
    if v is None:
        return '￿'
    s = str(v).strip()
    return s if s else '￿'


def _sort_key_raw(c: dict) -> tuple:
    """
    Chave canônica de um candidato para detecção de empate.
    Dois candidatos com raw keys idênticas são verdadeiramente empatados.
    Tupla: (frag_float, lab_float, iso_float, massa_float, formula_str).
    """
    return (
        _frag_key(c.get('score_fragmentacao')),
        _numeric_key_desc(c.get('score_lab')),
        _numeric_key_desc(c.get('score_isotopo')),
        _mass_key_asc(c.get('mass_error_ppm')),
        _formula_key_asc(c.get('formula')),
    )


def _sort_key_sortable(c: dict) -> tuple:
    """
    Chave ordenável para sorted() ascendente.
    Critérios descendentes (frag, lab, iso) são negados para que valores maiores
    apareçam primeiro na ordenação ascendente.
    Critérios ascendentes (massa, formula) mantêm seus valores originais.
    """
    raw = _sort_key_raw(c)
    return (
        -raw[0],  # fragmentacao: maior é melhor → nega para sort asc
        -raw[1],  # score_lab:    maior é melhor → nega
        -raw[2],  # isotopo:      maior é melhor → nega
         raw[3],  # massa:        menor abs é melhor → mantém
         raw[4],  # formula:      alfabético → mantém (string)
    )


def _find_distinguishing_criterion(key_better: tuple, key_worse: tuple) -> str:
    """
    Retorna o nome do primeiro critério onde duas raw keys diferem.
    key_better = candidato de rank superior; key_worse = rank inferior.
    """
    for k_a, k_b, nome in zip(key_better, key_worse, _CRITERIO_NAMES):
        if k_a != k_b:
            return nome
    return 'empate_humano'


def _ranking_hierarquico_grupo(candidatos: list) -> list:
    """
    Aplica o ranking hierárquico IST a um grupo de candidatos do mesmo composto.

    Modifica cada dict da lista in-place, adicionando:
        rank_posicao      (int)  : rank denso 1-based; empatados compartilham o mesmo valor
        rank_group        (int)  : mesmo que rank_posicao (campo explícito de grupo)
        is_tied           (bool) : True quando múltiplos candidatos dividem rank_posicao
        criterio_desempate (str) : critério que resolveu (ou não) o empate
        ranking_metodo    (str)  : 'hierarquico_ist'

    Semântica de criterio_desempate:
        Rank 1  → critério que separa rank 1 do rank 2 (o que "ganhou")
        Rank N  → critério que separa este grupo do grupo acima
        Empate  → 'empate_humano' (todos os 5 critérios idênticos, decisão humana)
        Único   → 'unico' (único candidato ou único grupo)
    """
    if not candidatos:
        return candidatos

    for c in candidatos:
        c['_raw']  = _sort_key_raw(c)
        c['_sort'] = _sort_key_sortable(c)

    sorted_cands = sorted(candidatos, key=lambda c: c['_sort'])

    # Agrupa candidatos com raw keys idênticas (empates verdadeiros)
    groups: list = []
    current: list = [sorted_cands[0]]
    for cand in sorted_cands[1:]:
        if cand['_raw'] == current[0]['_raw']:
            current.append(cand)
        else:
            groups.append(current)
            current = [cand]
    groups.append(current)

    dense_rank = 1
    for g_idx, group in enumerate(groups):
        is_tied = len(group) > 1

        if is_tied:
            criterio = 'empate_humano'
        elif len(groups) == 1:
            criterio = 'unico'
        elif g_idx == 0:
            criterio = _find_distinguishing_criterion(
                group[0]['_raw'], groups[1][0]['_raw']
            )
        else:
            criterio = _find_distinguishing_criterion(
                groups[g_idx - 1][0]['_raw'], group[0]['_raw']
            )

        for c in group:
            c['rank_posicao']       = dense_rank
            c['rank_group']         = dense_rank
            c['is_tied']            = is_tied
            c['criterio_desempate'] = criterio
            c['ranking_metodo']     = 'hierarquico_ist'

        dense_rank += 1

    for c in sorted_cands:
        c.pop('_raw',  None)
        c.pop('_sort', None)

    return sorted_cands


# ---------------------------------------------------------------------------
# Funções de scoring (diagnóstico / legado)
# ---------------------------------------------------------------------------

def _to_01(value, max_val: float) -> "float | None":
    """
    Normaliza value para [0,1] dividindo por max_val.
    Retorna None se value for nulo, NaN ou inválido.
    """
    if value is None:
        return None
    try:
        f = float(value)
        if pd.isna(f):
            return None
        return max(0.0, min(1.0, f / max_val))
    except (TypeError, ValueError):
        return None


def _score_massa_ppm(row: pd.Series) -> float:
    """
    Retorna score_massa (0–40) baseado em erro relativo em ppm.

    Hierarquia de fontes:
      1. mass_error_ppm  — fornecido diretamente pelo instrumento (preferido;
                           já corrigido para o aducto pelo software do equipamento)
      2. neutral_mass_da vs peso_molecular — calculado como fallback quando
                           mass_error_ppm não está disponível
      3. 0.0             — quando nenhuma das fontes acima está disponível
    """
    ppm: "float | None" = None

    raw_ppm = row.get("mass_error_ppm")
    if raw_ppm is not None:
        try:
            v = float(raw_ppm)
            if not pd.isna(v):
                ppm = abs(v)
        except (TypeError, ValueError):
            pass

    if ppm is None:
        neutral = row.get("neutral_mass_da")
        teorico = row.get("peso_molecular")
        if neutral is not None and teorico is not None:
            try:
                n, t = float(neutral), float(teorico)
                if not pd.isna(n) and not pd.isna(t) and t > 0:
                    ppm = abs(n - t) / t * 1e6
            except (TypeError, ValueError):
                pass

    if ppm is None:
        return 0.0

    if ppm <= TOLERANCIA_PPM_MAX:
        return 40.0
    if ppm >= TOLERANCIA_PPM_ZERO:
        return 0.0
    faixa = TOLERANCIA_PPM_ZERO - TOLERANCIA_PPM_MAX
    return 40.0 * (1 - (ppm - TOLERANCIA_PPM_MAX) / faixa)


def _normalizar_score_massa(row) -> "float | None":
    """
    Retorna score_massa normalizado para [0,1], ou None se não há
    fonte de dado ppm disponível (exclui do cálculo de ranking).
    """
    has_data = (
        row.get("mass_error_ppm") is not None
        or (
            row.get("neutral_mass_da") is not None
            and row.get("peso_molecular") is not None
        )
    )
    if not has_data:
        return None
    return _score_massa_ppm(row) / 40.0


def _calcular_score_ranking(row) -> float:
    """
    Média ponderada linear dos scores de identificação molecular, normalizada
    para escala 0–100.

    Cada componente é normalizado para [0,1] antes de entrar na fórmula.
    Componentes nulos são excluídos e os pesos restantes são renormalizados
    automaticamente, preservando a proporção relativa entre eles.

    Pesos configurados em W_FRAG / W_LAB / W_ISO / W_MASSA (ver constantes).
    """
    componentes: list = [
        (W_FRAG,  _to_01(row.get("score_fragmentacao"), 100.0)),
        (W_LAB,   _to_01(row.get("score_lab"),          100.0)),
        (W_ISO,   _to_01(row.get("score_isotopo"),      100.0)),
        (W_MASSA, _normalizar_score_massa(row)),
    ]
    validos = [(w, v) for w, v in componentes if v is not None]
    if not validos:
        return 0.0
    soma_pesos = sum(w for w, _ in validos)
    return round(sum(w * v for w, v in validos) / soma_pesos * 100, 4)


def _calcular_score_data_quality(row) -> float:
    """
    Percentual de metadados externos preenchidos (0–100%).

    Avalia os 5 campos de enriquecimento via API (PubChem + ChEBI).
    NÃO entra no cálculo de rank_posicao — serve exclusivamente como
    indicador de completude de dados para a interface e relatórios.
    """
    ok = sum(
        1 for campo in _CAMPOS_DATA_QUALITY
        if row.get(campo) is not None
        and str(row.get(campo)).strip() not in ("", "None", "Nao classificada")
    )
    return round(ok / len(_CAMPOS_DATA_QUALITY) * 100, 1)


# ---------------------------------------------------------------------------
# Funções de persistência (inserção nas tabelas do modelo)
# ---------------------------------------------------------------------------

def _inserir_sinal(
    cursor: sqlite3.Cursor,
    batch_id: int,
    compound_code: str,
    mz: float,
    retention_time,
) -> int:
    """
    Insere o sinal em fact_sinal scoped pelo batch e retorna seu id.
    UNIQUE(compound_code, batch_id) garante idempotência por batch.
    """
    cursor.execute(
        """
        INSERT OR IGNORE INTO fact_sinal (batch_id, compound_code, mz, retention_time)
        VALUES (?, ?, ?, ?)
        """,
        (batch_id, compound_code, mz, retention_time),
    )
    cursor.execute(
        "SELECT id FROM fact_sinal WHERE batch_id = ? AND compound_code = ?",
        (batch_id, compound_code),
    )
    return cursor.fetchone()[0]


def _inserir_molecula(cursor: sqlite3.Cursor, row: pd.Series) -> Tuple[int, bool]:
    """
    Insere a molécula em dim_molecula e retorna (id, is_nova).

    dim_molecula é um cache global cross-batch (nome UNIQUE globalmente).
    is_nova=True indica que a molécula não existia antes — útil para
    contabilizar chamadas de API efetivas.
    """
    nome = str(row["description"])
    cursor.execute("SELECT id FROM dim_molecula WHERE nome = ?", (nome,))
    existente = cursor.fetchone()
    if existente:
        return existente[0], False   # cache hit — sem chamada de API

    cursor.execute(
        """
        INSERT OR IGNORE INTO dim_molecula
            (nome, formula, peso_molecular, pubchem_cid, chebi_id, classe_quimica)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            nome,
            row.get("formula"),
            row.get("peso_molecular"),
            row.get("pubchem_cid"),
            row.get("chebi_id"),
            row.get("classe_quimica"),
        ),
    )
    cursor.execute("SELECT id FROM dim_molecula WHERE nome = ?", (nome,))
    return cursor.fetchone()[0], True   # nova molécula inserida


def _inserir_candidato(
    cursor: sqlite3.Cursor,
    batch_id: int,
    sinal_id: int,
    molecula_id: int,
    score_massa: float,
    score_ranking: float,
    score_data_quality: float,
    score_lab,
    score_fragmentacao,
    mass_error_ppm,
    score_isotopo,
    neutral_mass_da,
    adducts,
) -> None:
    """
    Registra a relação sinal ↔ candidato com batch_id, scores e dados laboratoriais.

    score_total e score_metadata são mantidos como aliases de backward compatibility
    para views e código existente que ainda referencie os nomes antigos.
    INSERT OR IGNORE evita duplicata se o par (sinal_id, molecula_id) já existir.
    """
    cursor.execute(
        """
        INSERT OR IGNORE INTO candidato_sinal (
            batch_id, sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa,
            score_ranking,      score_data_quality,
            score_total,        score_metadata
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id, sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa,
            score_ranking,      score_data_quality,
            score_ranking,      score_data_quality,   # aliases backward compat
        ),
    )


def _atualizar_ranking_hierarquico(cursor: sqlite3.Cursor, batch_id: int) -> None:
    """
    Aplica o ranking hierárquico IST a todos os candidatos do batch e persiste
    rank_posicao, rank_group, is_tied, criterio_desempate e ranking_metodo.

    Busca os candidatos do DB (com formula via JOIN em dim_molecula), agrupa
    por sinal, chama _ranking_hierarquico_grupo() e executa bulk UPDATE.

    score_ranking é preservado inalterado como coluna diagnóstica/legada.
    Scoped por batch_id — batches anteriores não são afetados.
    """
    cursor.execute(
        """
        SELECT
            c.id,
            c.sinal_id,
            c.score_fragmentacao,
            c.score_lab,
            c.score_isotopo,
            c.mass_error_ppm,
            m.formula
        FROM candidato_sinal c
        JOIN dim_molecula m ON c.molecula_id = m.id
        WHERE c.batch_id = ?
        """,
        (batch_id,),
    )
    cols = ('id', 'sinal_id', 'score_fragmentacao', 'score_lab',
            'score_isotopo', 'mass_error_ppm', 'formula')
    candidatos = [dict(zip(cols, row)) for row in cursor.fetchall()]

    grupos: dict = {}
    for c in candidatos:
        grupos.setdefault(c['sinal_id'], []).append(c)

    updates = []
    for grupo in grupos.values():
        for c in _ranking_hierarquico_grupo(grupo):
            updates.append((
                c['rank_posicao'],
                c['rank_group'],
                1 if c['is_tied'] else 0,
                c['criterio_desempate'],
                c['ranking_metodo'],
                c['id'],
            ))

    if updates:
        cursor.executemany(
            """
            UPDATE candidato_sinal SET
                rank_posicao       = ?,
                rank_group         = ?,
                is_tied            = ?,
                criterio_desempate = ?,
                ranking_metodo     = ?
            WHERE id = ?
            """,
            updates,
        )

    logger.info(
        f"Ranking hierárquico IST: {len(grupos)} sinais, "
        f"{len(updates)} candidatos atualizados (batch {batch_id})."
    )


def carregar_dados_no_banco(df: pd.DataFrame, batch_id: int) -> dict:
    """
    Distribui o DataFrame enriquecido nas três tabelas do modelo, scoped
    pelo batch_id fornecido:
        fact_sinal       → medição bruta do equipamento (por batch)
        dim_molecula     → metadados da molécula (cache global cross-batch)
        candidato_sinal  → relação N:N com scores de identificação (por batch)

    Retorna dict com estatísticas:
        sinais          — número de sinais únicos inseridos
        candidatos      — número de candidatos inseridos
        moleculas_novas — moléculas não existentes antes deste batch
        erros           — linhas ignoradas por erro
    """
    if df is None or df.empty:
        logger.warning("Nenhum dado para carregar no banco.")
        return {"sinais": 0, "candidatos": 0, "moleculas_novas": 0, "erros": 0}

    logger.info(f"Carregando {len(df)} registros no banco (batch_id={batch_id})...")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        erros = 0
        sinais_inseridos: set = set()
        candidatos_inseridos = 0
        moleculas_novas = 0

        for idx, row in df.iterrows():
            try:
                mz = row["mz"]

                sinal_id = _inserir_sinal(
                    cursor, batch_id, row["compound_code"], mz, row.get("retention_time")
                )
                sinais_inseridos.add(sinal_id)

                molecula_id, is_nova = _inserir_molecula(cursor, row)
                if is_nova:
                    moleculas_novas += 1

                score_massa       = _score_massa_ppm(row)
                score_ranking     = _calcular_score_ranking(row)
                score_data_quality = _calcular_score_data_quality(row)

                _inserir_candidato(
                    cursor, batch_id, sinal_id, molecula_id,
                    score_massa        = score_massa,
                    score_ranking      = score_ranking,
                    score_data_quality = score_data_quality,
                    score_lab          = _to_float(row.get("score_lab")),
                    score_fragmentacao = _to_float(row.get("score_fragmentacao")),
                    mass_error_ppm     = _to_float(row.get("mass_error_ppm")),
                    score_isotopo      = _to_float(row.get("score_isotopo")),
                    neutral_mass_da    = _to_float(row.get("neutral_mass_da")),
                    adducts            = row.get("adducts"),
                )
                candidatos_inseridos += 1

            except Exception as e:
                logger.warning(f"Linha {idx} ignorada por erro: {e}")
                erros += 1

        _atualizar_ranking_hierarquico(cursor, batch_id)
        conn.commit()

        logger.info(
            f"Carga concluída: {len(sinais_inseridos)} sinais, "
            f"{candidatos_inseridos} candidatos, "
            f"{moleculas_novas} moléculas novas, {erros} erros."
        )
        return {
            "sinais":          len(sinais_inseridos),
            "candidatos":      candidatos_inseridos,
            "moleculas_novas": moleculas_novas,
            "erros":           erros,
        }

    except Exception as e:
        logger.error(f"Erro crítico na carga: {e}")
        return {"sinais": 0, "candidatos": 0, "moleculas_novas": 0, "erros": -1}
    finally:
        if "conn" in locals():
            conn.close()


def _to_float(valor) -> "float | None":
    """Converte para float ou retorna None se o valor for nulo/inválido."""
    if valor is None:
        return None
    try:
        f = float(valor)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
