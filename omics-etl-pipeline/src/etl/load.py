import pandas as pd
import sqlite3
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.connection import DB_PATH

logger = logging.getLogger(__name__)

def carregar_dados_no_banco(df: pd.DataFrame) -> bool:
    if df is None or df.empty:
        logger.warning("Nenhum dado para carregar na base de dados.")
        return False
        
    logger.info(f"Iniciando a carga de {len(df)} registos no Modelo Dimensional...")
    
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        
        # Iterar sobre as linhas do DataFrame para respeitar a integridade referencial
        for _, row in df.iterrows():
            
            # 1. Inserir na dimensão (o comando IGNORE salta se a molécula já existir)
            cursor.execute("""
                INSERT OR IGNORE INTO dim_composto 
                (compound_code, description, formula, pubchem_cid, chebi_id, classe_quimica)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                row['compound_code'], 
                str(row['description']), 
                row.get('formula'), 
                row.get('pubchem_cid'), 
                row.get('chebi_id'), 
                row.get('classe_quimica')
            ))
            
            # 2. Descobrir qual é o ID da molécula (seja recém-criada ou já existente)
            cursor.execute("""
                SELECT id FROM dim_composto 
                WHERE compound_code = ? AND description = ?
            """, (row['compound_code'], str(row['description'])))
            
            resultado = cursor.fetchone()
            if resultado:
                dim_id = resultado[0]
                
                # 3. Inserir na tabela de factos usando o ID da dimensão como Chave Estrangeira
                cursor.execute("""
                    INSERT INTO fact_abundancia 
                    (dim_composto_id, mz, retention_time)
                    VALUES (?, ?, ?)
                """, (dim_id, row['mz'], row['retention_time']))
            
        conn.commit()
        logger.info("✅ Carga Dimensional concluída com sucesso!")
        return True
        
    except Exception as e:
        logger.error(f"Erro inesperado ao guardar no modelo dimensional: {e}")
        return False
    finally:
        if 'conn' in locals():
            conn.close()