import pandas as pd
import logging
from pathlib import Path
from typing import Optional

# 1. Configuração Profissional de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def extrair_dados_brutos(caminho_ident: Path, caminho_abund: Path) -> Optional[pd.DataFrame]:
    """
    Lê os ficheiros brutos do equipamento analítico e realiza o cruzamento (merge).
    
    Args:
        caminho_ident (Path): Caminho para o ficheiro de identificação (ex: IDENTIFICACAO.xlsx/csv).
        caminho_abund (Path): Caminho para o ficheiro de abundância (ex: ABUND.xlsx/csv).
        
    Returns:
        pd.DataFrame: DataFrame consolidado com os dados, ou None em caso de falha.
    """
    logger.info("Iniciando a extração da Camada Raw...")

    try:
        # Validação de existência dos ficheiros
        if not caminho_ident.exists():
            logger.error(f"Ficheiro não encontrado: {caminho_ident}")
            return None
        if not caminho_abund.exists():
            logger.error(f"Ficheiro não encontrado: {caminho_abund}")
            return None

        # Leitura dos dados
        logger.info("Lendo ficheiros CSV/Excel para a memória...")
        df_ident = pd.read_csv(caminho_ident, encoding='latin1', sep=';')
        df_abund = pd.read_csv(caminho_abund, encoding='latin1', sep=';')

        # Cruzamento (Merge) usando a coluna padrão do equipamento 'Compound'
        logger.info("Realizando o cruzamento (Merge) entre Identificação e Abundância...")
        df_consolidado = pd.merge(df_ident, df_abund, on='Compound', how='inner')

        # Limpeza inicial: Remover linhas que não têm nome de molécula
        if 'Description' in df_consolidado.columns:
            linhas_antes = len(df_consolidado)
            df_consolidado = df_consolidado.dropna(subset=['Description'])
            linhas_removidas = linhas_antes - len(df_consolidado)
            logger.info(f"Limpeza: {linhas_removidas} linhas sem identificação removidas.")

        logger.info(f"✅ Extração concluída! Total de registos válidos: {len(df_consolidado)}")
        return df_consolidado

    except Exception as e:
        logger.critical(f"Falha crítica na extração de dados: {e}")
        return None

# Bloco de execução isolada (Para testes locais)
if __name__ == "__main__":
    # Define caminhos absolutos de forma dinâmica e à prova de falhas
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    RAW_DIR = BASE_DIR / 'data' / 'raw'
    
    # Nomes dos ficheiros que o IST enviou
    ARQUIVO_IDENT = RAW_DIR / "IDENTIFICACAO.xlsx"
    ARQUIVO_ABUND = RAW_DIR / "ABUND.xlsx"
    
    df_resultado = extrair_dados_brutos(ARQUIVO_IDENT, ARQUIVO_ABUND)
    
    if df_resultado is not None:
        print("\nPré-visualização do DataFrame Consolidado:")
        # Mostra as colunas essenciais que vamos enviar para a API
        print(df_resultado[['Compound', 'Description', 'm/z', 'Retention time (min)']].head())