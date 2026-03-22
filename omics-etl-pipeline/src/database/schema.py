import sqlite3
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

# DDL atual: o mesmo código do equipamento pode repetir-se com descrições diferentes (merge abundância).
SQL_TABELA_COMPOSTOS = """
    CREATE TABLE IF NOT EXISTS compostos_identificados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compound_code TEXT NOT NULL,
        description TEXT,
        mz REAL,
        retention_time REAL,
        formula TEXT,
        pubchem_cid TEXT,
        chebi_id TEXT,
        classe_quimica TEXT,
        via_metabolica TEXT,
        data_insercao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """


def _migrate_remover_unique_compound_code(conn: sqlite3.Connection) -> None:
    """Se a tabela foi criada com compound_code UNIQUE, recria sem essa restrição (preserva dados)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='compostos_identificados'"
    ).fetchone()
    if not row or not row[0]:
        return
    ddl = row[0]
    # Schema antigo: UNIQUE em compound_code (impedia várias linhas com o mesmo código)
    if "compound_code TEXT UNIQUE" not in ddl and "compound_code TEXT NOT NULL UNIQUE" not in ddl:
        return

    cur = conn.cursor()
    cur.execute("ALTER TABLE compostos_identificados RENAME TO compostos_identificados_old")
    cur.executescript(SQL_TABELA_COMPOSTOS)
    cur.execute(
        """
        INSERT INTO compostos_identificados (
            id, compound_code, description, mz, retention_time, formula,
            pubchem_cid, chebi_id, classe_quimica, via_metabolica, data_insercao
        )
        SELECT
            id, compound_code, description, mz, retention_time, formula,
            pubchem_cid, chebi_id, classe_quimica, via_metabolica, data_insercao
        FROM compostos_identificados_old
        """
    )
    cur.execute("DROP TABLE compostos_identificados_old")
    conn.commit()
    print("OK: Migração aplicada — removido UNIQUE de compound_code (várias linhas por código).")


def criar_tabelas():
    """
    Conecta ao banco SQLite e cria/atualiza o schema.
    """
    print("Iniciando a criação do Schema do Banco de Dados...")

    conn = sqlite3.connect(DB_PATH)
    try:
        existe = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='compostos_identificados'"
        ).fetchone()
        if existe:
            _migrate_remover_unique_compound_code(conn)

        conn.execute(SQL_TABELA_COMPOSTOS)
        conn.commit()
        print("OK: Tabela 'compostos_identificados' criada ou verificada com sucesso.")
    except sqlite3.Error as erro:
        print(f"Erro de banco de dados: {erro}")
    finally:
        conn.close()
        print("Conexão com o banco encerrada.")


if __name__ == "__main__":
    criar_tabelas()
