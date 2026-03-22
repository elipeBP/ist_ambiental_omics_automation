import sqlite3
import os

# Caminho absoluto para o arquivo do banco de dados na raiz do projeto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'banco_ist.db')

def criar_tabelas():
    """
    Conecta ao banco SQLite e executa os comandos DDL (Data Definition Language)
    para criar as tabelas do nosso projeto.
    """
    print("Iniciando a criação do Schema do Banco de Dados...")
    
    # Conecta ao banco (se não existir, ele cria o arquivo na hora)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Comando SQL para criar a tabela principal
    # Usamos IF NOT EXISTS para não dar erro se rodarmos o script duas vezes
    sql_criar_tabela_compostos = """
    CREATE TABLE IF NOT EXISTS compostos_identificados (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compound_code TEXT UNIQUE NOT NULL,    -- Ex: '9.03_455.2837n' (Vem do equipamento)
        description TEXT,                      -- Nome da molécula (Vem do Excel)
        mz REAL,                               -- Massa/Carga
        retention_time REAL,                   -- Tempo de retenção (min)
        formula TEXT,                          -- Fórmula química bruta
        pubchem_cid TEXT,                      -- ID que vamos buscar na API do PubChem
        chebi_id TEXT,                         -- ID da Ontologia que vem do PubChem
        classe_quimica TEXT,                   -- Classificação que vamos buscar no libChEBIpy
        via_metabolica TEXT,                   -- Taxonomia/Via
        data_insercao TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    try:
        # Executa o comando SQL
        cursor.execute(sql_criar_tabela_compostos)
        
        # Salva as alterações (Commit)
        conn.commit()
        print("✅ Tabela 'compostos_identificados' criada ou verificada com sucesso!")
        
    except sqlite3.Error as erro:
        print(f"❌ Erro de banco de dados: {erro}")
        
    finally:
        # Sempre fechar a conexão no final
        cursor.close()
        conn.close()
        print("Conexão com o banco encerrada.")

# Permite testar o arquivo diretamente
if __name__ == "__main__":
    criar_tabelas()