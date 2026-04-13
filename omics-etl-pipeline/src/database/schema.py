import sqlite3
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabela 1 — Sinal analítico bruto do equipamento
#   Cada linha representa uma medição única (compound_code é a chave natural).
# ---------------------------------------------------------------------------
SQL_FACT_SINAL = """
CREATE TABLE IF NOT EXISTS fact_sinal (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_code  TEXT NOT NULL UNIQUE,
    mz             REAL NOT NULL,
    retention_time REAL,
    abundancia     REAL,
    data_insercao  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Tabela 2 — Moléculas candidatas (enriquecidas pelas APIs)
#   Armazena o conhecimento externo de cada molécula.
#   Via_metabolica reservado para integração futura com HMDB.
# ---------------------------------------------------------------------------
SQL_DIM_MOLECULA = """
CREATE TABLE IF NOT EXISTS dim_molecula (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    nome           TEXT NOT NULL UNIQUE,
    formula        TEXT,
    peso_molecular REAL,
    pubchem_cid    TEXT,
    chebi_id       TEXT,
    classe_quimica TEXT,
    via_metabolica TEXT,
    data_insercao  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# ---------------------------------------------------------------------------
# Tabela 3 — Relação N:N entre sinais e candidatos
#   Núcleo do sistema: cada sinal pode ter vários candidatos,
#   cada candidato tem seus scores e posição no ranking.
# ---------------------------------------------------------------------------
SQL_CANDIDATO_SINAL = """
CREATE TABLE IF NOT EXISTS candidato_sinal (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sinal_id       INTEGER NOT NULL REFERENCES fact_sinal(id),
    molecula_id    INTEGER NOT NULL REFERENCES dim_molecula(id),
    score_massa    REAL DEFAULT 0,
    score_metadata REAL DEFAULT 0,
    score_total    REAL DEFAULT 0,
    rank_posicao   INTEGER,
    data_calculo   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(sinal_id, molecula_id)
);
"""

# ---------------------------------------------------------------------------
# Índices
# ---------------------------------------------------------------------------
SQL_INDICE_SINAL = """
CREATE INDEX IF NOT EXISTS idx_compound_code
    ON fact_sinal (compound_code);
"""

SQL_INDICE_RANK = """
CREATE INDEX IF NOT EXISTS idx_candidato_rank
    ON candidato_sinal (sinal_id, rank_posicao);
"""

# ---------------------------------------------------------------------------
# View final — ranking de candidatos por sinal (entrada para dashboard)
# ---------------------------------------------------------------------------
SQL_VIEW_RANKING = """
CREATE VIEW IF NOT EXISTS vw_ranking_candidatos AS
SELECT
    s.compound_code  AS "Sinal",
    s.mz             AS "m/z Medido",
    m.nome           AS "Candidato",
    m.formula        AS "Formula",
    m.peso_molecular AS "Peso Teorico",
    m.classe_quimica AS "Classe Quimica",
    c.score_massa    AS "Score Massa",
    c.score_metadata AS "Score Metadata",
    c.score_total    AS "Score Total",
    c.rank_posicao   AS "Rank"
FROM candidato_sinal c
JOIN fact_sinal   s ON c.sinal_id   = s.id
JOIN dim_molecula m ON c.molecula_id = m.id
ORDER BY s.compound_code, c.rank_posicao;
"""


def criar_tabelas() -> None:
    """Cria o schema completo do banco. Seguro para re-execução (IF NOT EXISTS)."""
    logger.info("Inicializando schema do banco de dados...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        cur = conn.cursor()
        cur.execute(SQL_FACT_SINAL)
        cur.execute(SQL_DIM_MOLECULA)
        cur.execute(SQL_CANDIDATO_SINAL)
        cur.execute(SQL_INDICE_SINAL)
        cur.execute(SQL_INDICE_RANK)
        cur.execute(SQL_VIEW_RANKING)
        conn.commit()
        logger.info(
            "Schema criado: fact_sinal | dim_molecula | candidato_sinal | vw_ranking_candidatos"
        )
    except sqlite3.Error as e:
        logger.error(f"Erro ao criar schema: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    criar_tabelas()
