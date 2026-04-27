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
# Funções de scoring
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


def _atualizar_ranking(cursor: sqlite3.Cursor, batch_id: int) -> None:
    """
    Calcula rank_posicao usando score_ranking para os candidatos do batch atual.
    Rank 1 = maior score_ranking dentro do sinal.

    Scoped por batch_id: rankings de batches anteriores ficam intactos.
    """
    cursor.execute(
        """
        UPDATE candidato_sinal
        SET rank_posicao = (
            SELECT COUNT(*) + 1
            FROM candidato_sinal cs2
            WHERE cs2.sinal_id     = candidato_sinal.sinal_id
              AND cs2.batch_id     = candidato_sinal.batch_id
              AND cs2.score_ranking > candidato_sinal.score_ranking
        )
        WHERE batch_id = ?
        """,
        (batch_id,),
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

        _atualizar_ranking(cursor, batch_id)
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
