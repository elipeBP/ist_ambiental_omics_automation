import os
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


def _ler_tabela(caminho: Path) -> pd.DataFrame:
    """Lê CSV (sep `;`, latin1) ou Excel (.xlsx via openpyxl)."""
    suf = caminho.suffix.lower()
    if suf in (".xlsx", ".xlsm"):
        return pd.read_excel(caminho, engine="openpyxl")
    if suf == ".xls":
        return pd.read_excel(caminho)
    return pd.read_csv(caminho, encoding="latin1", sep=";")


def _normalizar_colunas_apos_merge(df: pd.DataFrame) -> pd.DataFrame:
    """
    Após merge, o pandas renomeia colunas iguais com _x / _y.
    Unifica nomes esperados pelo restante do pipeline (ex.: transform.py).
    Prioridade: coluna da direita (_y), típica de abundância.
    """
    out = df.copy()

    for base in ("m/z", "Retention time (min)"):
        if base in out.columns:
            continue
        for suf in ("_y", "_x"):
            alt = f"{base}{suf}"
            if alt in out.columns:
                out[base] = out[alt]
                break

    if "Description" not in out.columns and "Description_x" in out.columns:
        out["Description"] = out["Description_x"]

    drop_candidates = [
        c
        for c in out.columns
        if c.endswith("_x") or c.endswith("_y")
    ]
    # Mantém só o que sobrou duplicado; remove sufixos já copiados para canonical
    out = out.drop(columns=[c for c in drop_candidates if c in out.columns], errors="ignore")
    return out


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
        df_ident = _ler_tabela(caminho_ident)
        df_abund = _ler_tabela(caminho_abund)

        # Cruzamento (Merge) usando a coluna padrão do equipamento 'Compound'
        logger.info("Realizando o cruzamento (Merge) entre Identificação e Abundância...")
        df_consolidado = pd.merge(df_ident, df_abund, on="Compound", how="inner")
        df_consolidado = _normalizar_colunas_apos_merge(df_consolidado)

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
    RAW_DIR = BASE_DIR / "data" / "raw"

    # Sobrescreva com variáveis de ambiente se os nomes forem outros, ex.:
    # $env:OMICS_IDENT_FILE = "IDENTIFICACAO.csv"; $env:OMICS_ABUND_FILE = "ABUND.csv"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")
    ARQUIVO_IDENT = RAW_DIR / nome_ident
    ARQUIVO_ABUND = RAW_DIR / nome_abund
    
    df_resultado = extrair_dados_brutos(ARQUIVO_IDENT, ARQUIVO_ABUND)
    
    if df_resultado is not None:
        print("\nPré-visualização do DataFrame Consolidado:")
        # Mostra as colunas essenciais que vamos enviar para a API
        desejadas = ["Compound", "Description", "m/z", "Retention time (min)"]
        cols = [c for c in desejadas if c in df_resultado.columns]
        if not cols:
            cols = list(df_resultado.columns)[:8]
        print(df_resultado[cols].head())