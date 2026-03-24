import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

# 1. Tabela de Dimensão (Guarda apenas os metadados da molécula e APIs)
SQL_CRIAR_DIMENSAO = """
CREATE TABLE IF NOT EXISTS dim_composto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compound_code TEXT NOT NULL,
    description TEXT,
    formula TEXT,
    pubchem_cid TEXT,
    chebi_id TEXT,
    classe_quimica TEXT,
    via_metabolica TEXT,
    data_insercao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(compound_code, description) -- Garante que não duplicamos moléculas idênticas
);
"""

# 2. Tabela de Factos (Guarda a telemetria do equipamento ligada à Dimensão)
SQL_CRIAR_FATO = """
CREATE TABLE IF NOT EXISTS fact_abundancia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dim_composto_id INTEGER,
    mz REAL,
    retention_time REAL,
    data_insercao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (dim_composto_id) REFERENCES dim_composto (id)
);
"""

# 3. Índice para acelerar as buscas exigido na Aula 5
SQL_CRIAR_INDICE = """
CREATE INDEX IF NOT EXISTS idx_compound_code ON dim_composto (compound_code);
"""

# 4. View de Enriquecimento exigida na Aula 5 (Analito | Massa | Usos)
SQL_CRIAR_VIEW = """
CREATE VIEW IF NOT EXISTS vw_enriquecimento_mol_usos AS
SELECT 
    d.description AS "Nome do Analito (IST)", 
    f.mz AS "Massa Molecular", 
    d.classe_quimica AS "Usos Conhecidos (API)"
FROM dim_composto d
JOIN fact_abundancia f ON d.id = f.dim_composto_id;
"""

def criar_tabelas():
    print("Iniciando a criação do Schema Dimensional (Facto/Dimensão)...")
    conn = sqlite3.connect(DB_PATH)
    
    # Habilitar o uso de chaves estrangeiras (Foreign Keys) no SQLite
    conn.execute("PRAGMA foreign_keys = ON;")
    
    try:
        cur = conn.cursor()
        cur.execute(SQL_CRIAR_DIMENSAO)
        cur.execute(SQL_CRIAR_FATO)
        cur.execute(SQL_CRIAR_INDICE)
        cur.execute(SQL_CRIAR_VIEW)
        conn.commit()
        print("✅ Schema dimensional, Índice e View criados com sucesso!")
    except sqlite3.Error as erro:
        print(f"❌ Erro de base de dados: {erro}")
    finally:
        conn.close()

if __name__ == "__main__":
    criar_tabelas()