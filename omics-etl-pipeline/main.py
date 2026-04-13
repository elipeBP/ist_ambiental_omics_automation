import logging
import os
import sys
from pathlib import Path

# Configuração de encoding para evitar erros com emojis no terminal do Windows
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Importando as nossas funções dos módulos ETL
from src.database.schema import criar_tabelas
from src.etl.extract import extrair_dados_brutos
from src.etl.transform import enriquecer_dados_laboratorio
from src.etl.load import carregar_dados_no_banco

# Configuração do Logger unificado
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def executar_pipeline():
    """
    Função principal que orquestra todo o processo de Engenharia de Dados.
    """
    logger.info("🚀 Iniciando o pipeline Omics ETL completo...")

    # 0. Garantir que o schema do banco existe antes de qualquer operação
    criar_tabelas()

    # 1. Definição dinâmica dos caminhos dos arquivos
    BASE_DIR = Path(__file__).resolve().parent
    RAW_DIR = BASE_DIR / "data" / "raw"
    
    # Um ficheiro por variável. Para CSV (ex. ER_ACETATO_SADIA), defina no PowerShell:
    # $env:OMICS_IDENT_FILE = "IDENTIFICACAO_ER_ACETATO_SADIA_.csv"
    # $env:OMICS_ABUND_FILE = "ABUND_ER_ACETATO_SADIA_NEG.csv"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")
    
    arquivo_ident = RAW_DIR / nome_ident
    arquivo_abund = RAW_DIR / nome_abund

    # --- ETAPA 1: EXTRAÇÃO (EXTRACT) ---
    logger.info("=== ETAPA 1: EXTRAÇÃO ===")
    df_bruto = extrair_dados_brutos(arquivo_ident, arquivo_abund)
    
    if df_bruto is None or df_bruto.empty:
        logger.error("❌ Pipeline abortado: Falha na extração dos dados brutos.")
        return

    # --- ETAPA 2: TRANSFORMAÇÃO (TRANSFORM) ---
    logger.info("=== ETAPA 2: TRANSFORMAÇÃO E ENRIQUECIMENTO ===")
    # Lembrete: O transform.py está configurado para testar apenas as 3 primeiras moléculas (.head(3))
    df_transformado = enriquecer_dados_laboratorio(df_bruto)
    
    if df_transformado is None or df_transformado.empty:
        logger.error("❌ Pipeline abortado: Falha na transformação dos dados.")
        return

    # --- ETAPA 3: CARGA (LOAD) ---
    logger.info("=== ETAPA 3: CARGA NO BANCO DE DADOS ===")
    sucesso_carga = carregar_dados_no_banco(df_transformado)
    
    if sucesso_carga:
        logger.info("🎉 Pipeline finalizado com sucesso absoluto! Dados prontos para o Dashboard.")
    else:
        logger.error("❌ Pipeline finalizado com erros na etapa de carga.")

if __name__ == "__main__":
    executar_pipeline()