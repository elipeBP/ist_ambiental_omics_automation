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
# Tabela 3 — Relação N:N sinal ↔ candidato com scores e dados laboratoriais
#
# Campos laboratoriais (do software do equipamento, via IDENTIFICACAO.xlsx):
#   score_lab          — Score calculado pelo software
#   score_fragmentacao — Fragmentation Score (MS/MS matching)
#   mass_error_ppm     — Mass Error em ppm (precisão analítica real)
#   score_isotopo      — Isotope Similarity (padrão isotópico)
#   neutral_mass_da    — Neutral mass (Da) por candidato, já com correção de aducto
#   adducts            — Tipo de aducto detectado ([M+H]+, [M-H]-, etc.)
#
# Campos de scoring interno (calculados pelo pipeline):
#   score_massa        — Baseado no desvio de massa (transitório até validação IST)
#   score_metadata     — Baseado na completude dos dados das APIs
#   score_total        — Soma ponderada (fórmula final a definir com IST)
# ---------------------------------------------------------------------------
SQL_CANDIDATO_SINAL = """
CREATE TABLE IF NOT EXISTS candidato_sinal (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    sinal_id           INTEGER NOT NULL REFERENCES fact_sinal(id),
    molecula_id        INTEGER NOT NULL REFERENCES dim_molecula(id),
    -- Dados laboratoriais do equipamento
    score_lab          REAL,
    score_fragmentacao REAL,
    mass_error_ppm     REAL,
    score_isotopo      REAL,
    neutral_mass_da    REAL,
    adducts            TEXT,
    -- Scores internos do pipeline
    score_massa        REAL DEFAULT 0,
    score_metadata     REAL DEFAULT 0,
    score_total        REAL DEFAULT 0,
    rank_posicao       INTEGER,
    data_calculo       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
# View final — exposição completa para o dashboard
# Inclui campos laboratoriais e scores internos lado a lado.
# A ponderação final do score_total será definida com o IST.
# ---------------------------------------------------------------------------
SQL_VIEW_RANKING = """
CREATE VIEW vw_ranking_candidatos AS
SELECT
    s.compound_code      AS "Sinal",
    s.mz                 AS "m/z Medido",
    m.nome               AS "Candidato",
    m.formula            AS "Formula",
    m.peso_molecular     AS "Peso Teorico",
    m.classe_quimica     AS "Classe Quimica",
    c.adducts            AS "Adducts",
    c.neutral_mass_da    AS "Neutral Mass (Da)",
    c.score_lab          AS "Score Lab",
    c.score_fragmentacao AS "Score Fragmentacao",
    c.mass_error_ppm     AS "Mass Error (ppm)",
    c.score_isotopo      AS "Isotope Similarity",
    c.score_massa        AS "Score Massa",
    c.score_metadata     AS "Score Metadata",
    c.score_total        AS "Score Total",
    c.rank_posicao       AS "Rank"
FROM candidato_sinal c
JOIN fact_sinal   s ON c.sinal_id   = s.id
JOIN dim_molecula m ON c.molecula_id = m.id
ORDER BY s.compound_code, c.rank_posicao;
"""

# ---------------------------------------------------------------------------
# Colunas laboratoriais adicionadas nesta versão.
# Usadas pela função de migração para bancos já existentes.
# ---------------------------------------------------------------------------
_MIGRACOES_CANDIDATO = [
    ("score_lab",          "REAL"),
    ("score_fragmentacao", "REAL"),
    ("mass_error_ppm",     "REAL"),
    ("score_isotopo",      "REAL"),
    ("neutral_mass_da",    "REAL"),
    ("adducts",            "TEXT"),
]


def _migrar_candidato_sinal(conn: sqlite3.Connection) -> None:
    """
    Adiciona as colunas laboratoriais ao candidato_sinal se ainda não existirem.
    Seguro para re-execução — ALTER TABLE falha silenciosamente se a coluna já existe.
    """
    cur = conn.cursor()
    for col_nome, col_tipo in _MIGRACOES_CANDIDATO:
        try:
            cur.execute(
                f"ALTER TABLE candidato_sinal ADD COLUMN {col_nome} {col_tipo}"
            )
            logger.info(f"Migração: candidato_sinal.{col_nome} adicionada.")
        except sqlite3.OperationalError:
            pass  # Coluna já existe — comportamento esperado em re-execuções


def criar_tabelas() -> None:
    """
    Cria o schema completo do banco e aplica migrações necessárias.

    Seguro para re-execução:
    - Tabelas: CREATE IF NOT EXISTS (não sobrescreve dados)
    - Colunas novas: ALTER TABLE (ignorado se já existe)
    - View: DROP + CREATE (sempre atualizada para refletir o schema atual)
    """
    logger.info("Inicializando schema do banco de dados...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        cur = conn.cursor()

        # Tabelas base (idempotentes)
        cur.execute(SQL_FACT_SINAL)
        cur.execute(SQL_DIM_MOLECULA)
        cur.execute(SQL_CANDIDATO_SINAL)
        cur.execute(SQL_INDICE_SINAL)
        cur.execute(SQL_INDICE_RANK)

        # Migração: adiciona colunas laboratoriais se o banco é pré-existente
        _migrar_candidato_sinal(conn)

        # View: sempre recriada para garantir que reflete o schema atual
        cur.execute("DROP VIEW IF EXISTS vw_ranking_candidatos")
        cur.execute(SQL_VIEW_RANKING)

        conn.commit()
        logger.info(
            "Schema OK: fact_sinal | dim_molecula | candidato_sinal | vw_ranking_candidatos"
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
