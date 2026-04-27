import sqlite3
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tabela 0 — Controle de execuções (rastreabilidade / auditoria)
# ---------------------------------------------------------------------------
SQL_BATCH_EXECUCAO = """
CREATE TABLE IF NOT EXISTS batch_execucao (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    status              TEXT NOT NULL DEFAULT 'pendente'
                            CHECK(status IN ('pendente','executando','sucesso','falha')),
    fonte               TEXT NOT NULL,
    nome_ident          TEXT NOT NULL,
    nome_abund          TEXT NOT NULL,
    hash_ident          TEXT NOT NULL,
    hash_abund          TEXT NOT NULL,
    iniciado_em         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    concluido_em        TIMESTAMP,
    total_sinais        INTEGER,
    total_candidatos    INTEGER,
    total_moleculas_api INTEGER,
    erro_mensagem       TEXT
    -- Deduplicação por hash feita em código (batch.py), não por constraint de DB.
    -- Isso permite retry após falha sem violar unicidade.
);
"""

SQL_INDICE_BATCH_STATUS = """
CREATE INDEX IF NOT EXISTS idx_batch_status
    ON batch_execucao (status, iniciado_em DESC);
"""

# ---------------------------------------------------------------------------
# Tabela 1 — Sinal analítico bruto do equipamento
#   compound_code único por batch (mesmo composto pode aparecer em experimentos
#   diferentes). batch_id é FK para batch_execucao.
# ---------------------------------------------------------------------------
SQL_FACT_SINAL = """
CREATE TABLE IF NOT EXISTS fact_sinal (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER NOT NULL REFERENCES batch_execucao(id),
    compound_code   TEXT NOT NULL,
    mz              REAL NOT NULL,
    retention_time  REAL,
    abundancia      REAL,
    data_insercao   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(compound_code, batch_id)
);
"""

# ---------------------------------------------------------------------------
# Tabela 2 — Moléculas candidatas (cache global de API)
#   nome UNIQUE globalmente: a mesma molécula não é consultada duas vezes
#   no PubChem/ChEBI, independente do batch em que aparecer (Fase 3).
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
# Tabela 3 — Relação N:N sinal ↔ candidato (com scores e dados laboratoriais)
#   batch_id desnormalizado: permite filtrar candidatos por batch sem JOIN
#   extra através de fact_sinal. O UNIQUE(sinal_id, molecula_id) é
#   implicitamente scoped por batch pois sinal_id já aponta para um sinal
#   de um batch específico.
# ---------------------------------------------------------------------------
SQL_CANDIDATO_SINAL = """
CREATE TABLE IF NOT EXISTS candidato_sinal (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id           INTEGER NOT NULL REFERENCES batch_execucao(id),
    sinal_id           INTEGER NOT NULL REFERENCES fact_sinal(id),
    molecula_id        INTEGER NOT NULL REFERENCES dim_molecula(id),
    -- Dados laboratoriais do equipamento (IDENTIFICACAO.xlsx)
    score_lab          REAL,
    score_fragmentacao REAL,
    mass_error_ppm     REAL,
    score_isotopo      REAL,
    neutral_mass_da    REAL,
    adducts            TEXT,
    -- Scores internos do pipeline (fórmula provisória — validação IST pendente)
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

SQL_INDICE_SINAL_BATCH = """
CREATE INDEX IF NOT EXISTS idx_sinal_batch
    ON fact_sinal (batch_id);
"""

SQL_INDICE_RANK = """
CREATE INDEX IF NOT EXISTS idx_candidato_rank
    ON candidato_sinal (sinal_id, rank_posicao);
"""

SQL_INDICE_CANDIDATO_BATCH = """
CREATE INDEX IF NOT EXISTS idx_candidato_batch
    ON candidato_sinal (batch_id);
"""

# ---------------------------------------------------------------------------
# View principal — batch mais recente com sucesso
#   Substitui a view anterior. Streamlit continua funcionando sem alterações
#   pois todas as colunas antigas estão presentes; Batch ID e Data Execucao
#   são colunas extras ignoradas pelo código existente.
# ---------------------------------------------------------------------------
SQL_VIEW_RANKING = """
CREATE VIEW vw_ranking_candidatos AS
SELECT
    b.id                 AS "Batch ID",
    b.iniciado_em        AS "Data Execucao",
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
JOIN fact_sinal      s ON c.sinal_id    = s.id
JOIN dim_molecula    m ON c.molecula_id = m.id
JOIN batch_execucao  b ON c.batch_id    = b.id
WHERE b.id = (SELECT MAX(id) FROM batch_execucao WHERE status = 'sucesso')
ORDER BY s.compound_code, c.rank_posicao;
"""

# ---------------------------------------------------------------------------
# View histórica — todos os batches com sucesso
#   Usada pelo seletor de batch histórico na UI (Fase 4).
# ---------------------------------------------------------------------------
SQL_VIEW_HISTORICO = """
CREATE VIEW vw_ranking_historico AS
SELECT
    b.id                 AS "Batch ID",
    b.iniciado_em        AS "Data Execucao",
    b.nome_ident         AS "Arquivo Ident",
    b.nome_abund         AS "Arquivo Abund",
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
JOIN fact_sinal      s ON c.sinal_id    = s.id
JOIN dim_molecula    m ON c.molecula_id = m.id
JOIN batch_execucao  b ON c.batch_id    = b.id
WHERE b.status = 'sucesso'
ORDER BY b.id DESC, s.compound_code, c.rank_posicao;
"""


def criar_tabelas() -> None:
    """
    Inicializa o schema completo e aplica migrações se necessário.

    Ordem de operações:
        1. Migração v1→v2 (se banco existente ainda não tem batch_id).
        2. CREATE IF NOT EXISTS de todas as tabelas (idempotente).
        3. DROP + CREATE das views (sempre refletem o schema atual).

    Seguro para re-execução em qualquer estado do banco.
    """
    from src.database.migrate import migrar_v1_para_v2

    logger.info("Inicializando schema do banco de dados...")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    try:
        # Migração antes de criar tabelas (batch_execucao já existe da Fase 1
        # em bancos atualizados, mas precisa existir antes da migração rodar)
        cur = conn.cursor()
        cur.execute(SQL_BATCH_EXECUCAO)
        cur.execute(SQL_INDICE_BATCH_STATUS)
        conn.commit()

        migrar_v1_para_v2(conn)

        # Tabelas restantes (idempotentes)
        cur.execute(SQL_FACT_SINAL)
        cur.execute(SQL_DIM_MOLECULA)
        cur.execute(SQL_CANDIDATO_SINAL)
        cur.execute(SQL_INDICE_SINAL)
        cur.execute(SQL_INDICE_SINAL_BATCH)
        cur.execute(SQL_INDICE_RANK)
        cur.execute(SQL_INDICE_CANDIDATO_BATCH)

        # Views: sempre recriadas para refletir o schema atual
        cur.execute("DROP VIEW IF EXISTS vw_ranking_candidatos")
        cur.execute("DROP VIEW IF EXISTS vw_ranking_historico")
        cur.execute(SQL_VIEW_RANKING)
        cur.execute(SQL_VIEW_HISTORICO)

        conn.commit()
        logger.info(
            "Schema OK: batch_execucao | fact_sinal | dim_molecula "
            "| candidato_sinal | vw_ranking_candidatos | vw_ranking_historico"
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
