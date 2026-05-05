"""
Utilitários de acesso ao banco para a interface Streamlit.

Toda a leitura de dados passa por aqui — as tabelas internas nunca são
acessadas diretamente pela UI.

Views disponíveis:
  vw_ranking_candidatos  → batch mais recente com sucesso (uso padrão)
  vw_ranking_historico   → todos os batches com sucesso (seletor histórico)
"""
import logging
import sqlite3
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH   = _BASE_DIR / "banco_ist.db"


def db_existe() -> bool:
    """Verifica se o arquivo do banco já foi criado pelo pipeline."""
    return DB_PATH.exists()


def carregar_ranking() -> pd.DataFrame:
    """
    Retorna todos os candidatos do batch mais recente com sucesso.
    Usa vw_ranking_candidatos (já filtra pelo batch mais recente).
    """
    if not db_existe():
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        return pd.read_sql_query('SELECT * FROM "vw_ranking_candidatos"', conn)
    except Exception as e:
        logger.error(f"Erro ao carregar ranking: {e}")
        return pd.DataFrame()
    finally:
        if "conn" in locals():
            conn.close()


def carregar_sinal(sinal: str) -> pd.DataFrame:
    """
    Retorna todos os candidatos de um sinal específico do batch mais recente,
    ordenados por Rank.
    """
    if not db_existe():
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        return pd.read_sql_query(
            'SELECT * FROM "vw_ranking_candidatos" WHERE "Sinal" = ? ORDER BY "Rank"',
            conn,
            params=(sinal,),
        )
    except Exception as e:
        logger.error(f"Erro ao carregar sinal '{sinal}': {e}")
        return pd.DataFrame()
    finally:
        if "conn" in locals():
            conn.close()


def listar_batches() -> list:
    """
    Retorna todos os batches registrados, do mais recente para o mais antigo.
    Delega para src.database.batch para evitar duplicação de lógica.
    """
    try:
        from src.database.batch import listar_batches as _listar
        return _listar()
    except Exception:
        return []


def carregar_ranking_batch(batch_id: int) -> pd.DataFrame:
    """
    Retorna o ranking completo de um batch específico via vw_ranking_historico.
    Usado pelo seletor de batch histórico na UI (Fase 4).
    """
    if not db_existe():
        return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        return pd.read_sql_query(
            'SELECT * FROM "vw_ranking_historico" WHERE "Batch ID" = ? ORDER BY "Sinal", "Rank"',
            conn,
            params=(batch_id,),
        )
    except Exception as e:
        logger.error(f"Erro ao carregar ranking do batch {batch_id}: {e}")
        return pd.DataFrame()
    finally:
        if "conn" in locals():
            conn.close()
