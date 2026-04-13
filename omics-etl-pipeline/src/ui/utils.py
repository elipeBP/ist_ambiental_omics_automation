"""
Utilitários de acesso ao banco para a interface Streamlit.

Toda a leitura de dados passa por aqui.
A view `vw_ranking_candidatos` é a única fonte de dados da UI — as tabelas
internas nunca são acessadas diretamente.
"""
import sqlite3
from pathlib import Path

import pandas as pd

# omics-etl-pipeline/src/ui/utils.py → sobe 3 níveis → omics-etl-pipeline/
_BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH   = _BASE_DIR / "banco_ist.db"

_VIEW = "vw_ranking_candidatos"


def db_existe() -> bool:
    """Verifica se o arquivo do banco já foi criado pelo pipeline."""
    return DB_PATH.exists()


def carregar_ranking() -> pd.DataFrame:
    """
    Lê todos os registros da view de ranking e retorna um DataFrame.

    Colunas retornadas (definidas pela view):
        Sinal, m/z Medido, Candidato, Formula, Peso Teorico,
        Classe Quimica, Score Massa, Score Metadata, Score Total, Rank

    Retorna DataFrame vazio se a view não tiver dados ou se o banco não existir.
    """
    if not db_existe():
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(f'SELECT * FROM "{_VIEW}"', conn)
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if "conn" in locals():
            conn.close()


def carregar_sinal(sinal: str) -> pd.DataFrame:
    """
    Retorna todos os candidatos de um sinal específico, ordenados por Rank.

    Args:
        sinal: Valor da coluna 'Sinal' (compound_code do equipamento).
    """
    if not db_existe():
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(
            f'SELECT * FROM "{_VIEW}" WHERE "Sinal" = ? ORDER BY "Rank"',
            conn,
            params=(sinal,),
        )
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        if "conn" in locals():
            conn.close()
