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
# Parâmetros do scoring interno
# (fórmula de score_total a validar com IST antes de tornar definitiva)
#
# Thresholds de ppm baseados em boas práticas de HRMS (Q-TOF / Orbitrap).
# Instrumentos modernos de alta resolução operam tipicamente a 1–5 ppm.
# Estes valores são defaults defensáveis — podem ser calibrados pelo IST
# conforme o equipamento utilizado (ex.: 2 ppm para Orbitrap, 10 ppm para Q-TOF).
# ---------------------------------------------------------------------------
TOLERANCIA_PPM_MAX  = 5.0   # ≤  5 ppm → score_massa = 40 (match excelente)
TOLERANCIA_PPM_ZERO = 20.0  # ≥ 20 ppm → score_massa = 0  (match descartado)

PONTOS_POR_METADADO = 6
CAMPOS_METADADO = ["formula", "pubchem_cid", "chebi_id", "classe_quimica", "peso_molecular"]


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


def _calcular_scores(row: pd.Series, mz_sinal: float) -> Tuple[float, float, float]:
    """
    Calcula score_massa, score_metadata e score_total para um candidato.
    Lógica provisória — ponderação final será definida com o IST.

    score_massa usa erro relativo em ppm (escala invariante de massa):
      - Fonte primária : mass_error_ppm do instrumento (já corrigido para aducto)
      - Fallback       : ppm calculado de neutral_mass_da vs peso_molecular
      - 2º fallback    : score_massa = 0 se ambas as fontes forem nulas
    """
    score_massa = _score_massa_ppm(row)

    presentes = sum(
        1 for campo in CAMPOS_METADADO
        if row.get(campo) is not None
        and str(row.get(campo)).strip() not in ("", "None", "Nao classificada")
    )
    score_metadata = presentes * PONTOS_POR_METADADO
    score_total = round(score_massa + score_metadata, 4)
    return round(score_massa, 4), round(score_metadata, 4), score_total


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
    contabilizar chamadas de API efetivas (Fase 3).
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
    score_metadata: float,
    score_total: float,
    score_lab,
    score_fragmentacao,
    mass_error_ppm,
    score_isotopo,
    neutral_mass_da,
    adducts,
) -> None:
    """
    Registra a relação sinal ↔ candidato com batch_id, dados laboratoriais e scores.
    INSERT OR IGNORE evita duplicata se o par (sinal_id, molecula_id) já existir.
    """
    cursor.execute(
        """
        INSERT OR IGNORE INTO candidato_sinal (
            batch_id, sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa, score_metadata, score_total
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id, sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa, score_metadata, score_total,
        ),
    )


def _atualizar_ranking(cursor: sqlite3.Cursor, batch_id: int) -> None:
    """
    Calcula rank_posicao somente para candidatos do batch atual.
    Rank 1 = maior score_total dentro do sinal.

    Scoped por batch_id: rankings de batches anteriores ficam intactos.
    """
    cursor.execute(
        """
        UPDATE candidato_sinal
        SET rank_posicao = (
            SELECT COUNT(*) + 1
            FROM candidato_sinal cs2
            WHERE cs2.sinal_id    = candidato_sinal.sinal_id
              AND cs2.batch_id    = candidato_sinal.batch_id
              AND cs2.score_total > candidato_sinal.score_total
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
        candidato_sinal  → relação N:N com dados laboratoriais e scores (por batch)

    Retorna dict com estatísticas:
        sinais        — número de sinais únicos inseridos
        candidatos    — número de candidatos inseridos
        moleculas_novas — moléculas não existentes antes deste batch
        erros         — linhas ignoradas por erro
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

                sinal_id = _inserir_sinal(cursor, batch_id, row["compound_code"], mz, row.get("retention_time"))
                sinais_inseridos.add(sinal_id)

                molecula_id, is_nova = _inserir_molecula(cursor, row)
                if is_nova:
                    moleculas_novas += 1

                score_massa, score_metadata, score_total = _calcular_scores(row, mz)

                _inserir_candidato(
                    cursor, batch_id, sinal_id, molecula_id,
                    score_massa, score_metadata, score_total,
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
