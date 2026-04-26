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
# ---------------------------------------------------------------------------
TOLERANCIA_MAXIMA = 0.5    # desvio ≤ 0.5 Da → score_massa = 40
TOLERANCIA_ZERO   = 5.0    # desvio ≥ 5.0 Da → score_massa = 0

PONTOS_POR_METADADO = 6
CAMPOS_METADADO = ["formula", "pubchem_cid", "chebi_id", "classe_quimica", "peso_molecular"]


def _calcular_scores(row: pd.Series, mz_sinal: float) -> Tuple[float, float, float]:
    """
    Calcula score_massa, score_metadata e score_total para um candidato.
    Lógica provisória — ponderação final será definida com o IST.
    """
    peso_molecular = row.get("peso_molecular")
    if peso_molecular is not None:
        try:
            delta = abs(float(mz_sinal) - float(peso_molecular))
            if delta <= TOLERANCIA_MAXIMA:
                score_massa = 40.0
            elif delta >= TOLERANCIA_ZERO:
                score_massa = 0.0
            else:
                faixa = TOLERANCIA_ZERO - TOLERANCIA_MAXIMA
                score_massa = 40.0 * (1 - (delta - TOLERANCIA_MAXIMA) / faixa)
        except (TypeError, ValueError):
            score_massa = 0.0
    else:
        score_massa = 0.0

    presentes = sum(
        1 for campo in CAMPOS_METADADO
        if row.get(campo) is not None
        and str(row.get(campo)).strip() not in ("", "None", "Nao classificada")
    )
    score_metadata = presentes * PONTOS_POR_METADADO
    score_total = round(score_massa + score_metadata, 4)
    return round(score_massa, 4), round(score_metadata, 4), score_total


def _inserir_sinal(
    cursor: sqlite3.Cursor, compound_code: str, mz: float, retention_time
) -> int:
    """Insere o sinal em fact_sinal e retorna seu id (idempotente via IGNORE)."""
    cursor.execute(
        """
        INSERT OR IGNORE INTO fact_sinal (compound_code, mz, retention_time)
        VALUES (?, ?, ?)
        """,
        (compound_code, mz, retention_time),
    )
    cursor.execute(
        "SELECT id FROM fact_sinal WHERE compound_code = ?",
        (compound_code,),
    )
    return cursor.fetchone()[0]


def _inserir_molecula(cursor: sqlite3.Cursor, row: pd.Series) -> int:
    """Insere a molécula em dim_molecula e retorna seu id (idempotente via IGNORE)."""
    cursor.execute(
        """
        INSERT OR IGNORE INTO dim_molecula
            (nome, formula, peso_molecular, pubchem_cid, chebi_id, classe_quimica)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(row["description"]),
            row.get("formula"),
            row.get("peso_molecular"),
            row.get("pubchem_cid"),
            row.get("chebi_id"),
            row.get("classe_quimica"),
        ),
    )
    cursor.execute(
        "SELECT id FROM dim_molecula WHERE nome = ?",
        (str(row["description"]),),
    )
    return cursor.fetchone()[0]


def _inserir_candidato(
    cursor: sqlite3.Cursor,
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
    Registra a relação sinal ↔ candidato com dados laboratoriais e scores internos.
    INSERT OR IGNORE evita duplicata se o par (sinal_id, molecula_id) já existir.
    """
    cursor.execute(
        """
        INSERT OR IGNORE INTO candidato_sinal (
            sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa, score_metadata, score_total
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sinal_id, molecula_id,
            score_lab, score_fragmentacao, mass_error_ppm,
            score_isotopo, neutral_mass_da, adducts,
            score_massa, score_metadata, score_total,
        ),
    )


def _atualizar_ranking(cursor: sqlite3.Cursor) -> None:
    """
    Calcula rank_posicao para todos os candidatos de cada sinal em lote.
    Rank 1 = maior score_total. Executado uma vez após todas as inserções.
    """
    cursor.execute("""
        UPDATE candidato_sinal
        SET rank_posicao = (
            SELECT COUNT(*) + 1
            FROM candidato_sinal cs2
            WHERE cs2.sinal_id = candidato_sinal.sinal_id
              AND cs2.score_total > candidato_sinal.score_total
        )
    """)


def carregar_dados_no_banco(df: pd.DataFrame) -> bool:
    """
    Distribui o DataFrame enriquecido nas três tabelas do modelo:
        fact_sinal       → medição bruta do equipamento
        dim_molecula     → metadados da molécula candidata (APIs)
        candidato_sinal  → relação N:N com dados laboratoriais e scores

    Retorna True se todos os registros foram inseridos sem erros.
    """
    if df is None or df.empty:
        logger.warning("Nenhum dado para carregar no banco.")
        return False

    logger.info(f"Iniciando carga de {len(df)} registros no banco...")

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()

        erros = 0
        for idx, row in df.iterrows():
            try:
                mz = row["mz"]

                sinal_id    = _inserir_sinal(cursor, row["compound_code"], mz, row.get("retention_time"))
                molecula_id = _inserir_molecula(cursor, row)

                score_massa, score_metadata, score_total = _calcular_scores(row, mz)

                _inserir_candidato(
                    cursor, sinal_id, molecula_id,
                    score_massa, score_metadata, score_total,
                    score_lab          = _to_float(row.get("score_lab")),
                    score_fragmentacao = _to_float(row.get("score_fragmentacao")),
                    mass_error_ppm     = _to_float(row.get("mass_error_ppm")),
                    score_isotopo      = _to_float(row.get("score_isotopo")),
                    neutral_mass_da    = _to_float(row.get("neutral_mass_da")),
                    adducts            = row.get("adducts"),
                )

            except Exception as e:
                logger.warning(f"Linha {idx} ignorada por erro: {e}")
                erros += 1

        _atualizar_ranking(cursor)
        conn.commit()

        carregados = len(df) - erros
        logger.info(f"Carga concluida: {carregados} inseridos, {erros} ignorados.")
        return erros == 0

    except Exception as e:
        logger.error(f"Erro critico na carga: {e}")
        return False
    finally:
        if "conn" in locals():
            conn.close()


def _to_float(valor) -> float | None:
    """Converte para float ou retorna None se o valor for nulo/inválido."""
    if valor is None:
        return None
    try:
        f = float(valor)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None
