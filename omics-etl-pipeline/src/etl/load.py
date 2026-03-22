import pandas as pd
import sqlite3
import logging
import sys
from pathlib import Path

# Configuração para o Python encontrar as nossas pastas 'src'
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

# Importamos o caminho do banco de dados que já criamos antes
from src.database.connection import DB_PATH

# Configuração do Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def carregar_dados_no_banco(df: pd.DataFrame) -> bool:
    """
    Recebe o DataFrame enriquecido e salva no banco de dados SQLite local.
    """
    if df is None or df.empty:
        logger.warning("Nenhum dado para carregar no banco.")
        return False
        
    logger.info(f"Iniciando a carga (Load) de {len(df)} registos no banco de dados...")
    
    try:
        # Conecta ao nosso arquivo banco_ist.db
        conn = sqlite3.connect(DB_PATH)
        
        # O Pandas tem uma função mágica (to_sql) que converte o DataFrame direto para comandos INSERT no SQL!
        # if_exists='append': adiciona as linhas na tabela que já existe.
        # index=False: impede que o índice (0, 1, 2...) do Pandas vire uma coluna no banco.
        df.to_sql(name='compostos_identificados', con=conn, if_exists='append', index=False)
        
        logger.info("✅ Carga concluída com sucesso! Dados guardados de forma segura no SQLite.")
        return True
        
    except sqlite3.IntegrityError as e:
        # Lembra que colocamos UNIQUE no compound_code lá no schema.py?
        # Se rodarmos o script duas vezes com a mesma planilha, ele bloqueia os duplicados aqui!
        logger.error(f"Erro de integridade (Dados duplicados ou chave repetida): {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado ao salvar no banco: {e}")
        return False
    finally:
        # Garante que a conexão com o banco seja fechada mesmo se der erro
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("Módulo Load pronto. A execução real será feita pelo arquivo main.py que vamos criar em breve!")
    