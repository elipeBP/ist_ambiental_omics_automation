"""
Validação de arquivos de entrada e cálculo de hash para deduplicação.

Executado antes do ETL iniciar — falhas aqui são amigáveis ao usuário,
não erros técnicos no meio do processamento.
"""
import hashlib
import logging
from pathlib import Path
from typing import NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)

COLUNAS_IDENT_OBRIGATORIAS = {"Compound", "Description"}
COLUNAS_ABUND_OBRIGATORIAS = {"Compound", "m/z"}
EXTENSOES_PERMITIDAS       = {".xlsx", ".xlsm", ".xls", ".csv"}
TAMANHO_MAXIMO_BYTES       = 50 * 1024 * 1024  # 50 MB


class BatchValidacaoError(Exception):
    """Input rejeitado antes do ETL — mensagem é legível pelo usuário."""


class BatchDuplicadoError(Exception):
    """Par de arquivos já processado com sucesso — nenhuma ação necessária."""


class ArquivosValidados(NamedTuple):
    hash_ident: str
    hash_abund: str


def validar_arquivos_entrada(
    caminho_ident: Path,
    caminho_abund: Path,
) -> ArquivosValidados:
    """
    Valida os arquivos de entrada de forma fail-fast antes de iniciar o ETL.

    Verificações (em ordem):
        1. Existência dos dois arquivos.
        2. Extensão permitida.
        3. Tamanho < 50 MB.
        4. Legibilidade (lê 5 linhas — detecta corrupção rapidamente).
        5. Colunas obrigatórias presentes em cada arquivo.
        6. Merge em 'Compound' produz pelo menos 1 linha.
        7. Cálculo dos hashes SHA-256 (só após todas as verificações).

    Levanta BatchValidacaoError com mensagem clara em qualquer falha.
    Retorna ArquivosValidados(hash_ident, hash_abund) no sucesso.
    """
    # 1. Existência
    for caminho, label in [(caminho_ident, "identificação"), (caminho_abund, "abundância")]:
        if not caminho.exists():
            raise BatchValidacaoError(
                f"Arquivo de {label} não encontrado: '{caminho.name}'\n"
                f"Caminho esperado: {caminho}"
            )

    # 2. Extensão
    for caminho in (caminho_ident, caminho_abund):
        if caminho.suffix.lower() not in EXTENSOES_PERMITIDAS:
            raise BatchValidacaoError(
                f"Formato não suportado: '{caminho.suffix}' ({caminho.name}). "
                f"Formatos aceitos: {', '.join(sorted(EXTENSOES_PERMITIDAS))}"
            )

    # 3. Tamanho
    for caminho, label in [(caminho_ident, "identificação"), (caminho_abund, "abundância")]:
        tamanho = caminho.stat().st_size
        if tamanho > TAMANHO_MAXIMO_BYTES:
            raise BatchValidacaoError(
                f"Arquivo de {label} '{caminho.name}' excede o limite de "
                f"{TAMANHO_MAXIMO_BYTES // (1024 * 1024)} MB "
                f"({tamanho // (1024 * 1024)} MB encontrado)."
            )

    # 4. Legibilidade + 5. Colunas obrigatórias
    df_ident = _ler_amostra(caminho_ident, "identificação")
    df_abund = _ler_amostra(caminho_abund, "abundância")
    _checar_colunas(df_ident, COLUNAS_IDENT_OBRIGATORIAS, caminho_ident.name, "identificação")
    _checar_colunas(df_abund, COLUNAS_ABUND_OBRIGATORIAS, caminho_abund.name, "abundância")

    # 6. Merge produz pelo menos 1 linha
    compostos_ident = set(df_ident["Compound"].dropna().astype(str))
    compostos_abund = set(df_abund["Compound"].dropna().astype(str))
    if not compostos_ident & compostos_abund:
        raise BatchValidacaoError(
            "Nenhum valor de 'Compound' em comum entre os arquivos de identificação "
            "e abundância. Verifique se os arquivos pertencem ao mesmo experimento.\n"
            f"  Identificação: {len(compostos_ident)} compostos únicos\n"
            f"  Abundância:    {len(compostos_abund)} compostos únicos"
        )

    # 7. Hashes — apenas após todas as validações passarem
    hash_ident = calcular_hash_arquivo(caminho_ident)
    hash_abund = calcular_hash_arquivo(caminho_abund)

    logger.info(
        f"Validação OK: {caminho_ident.name} + {caminho_abund.name} "
        f"({len(compostos_ident & compostos_abund)} compostos em comum)"
    )
    return ArquivosValidados(hash_ident=hash_ident, hash_abund=hash_abund)


def calcular_hash_arquivo(caminho: Path, chunk_size: int = 65536) -> str:
    """SHA-256 hex do conteúdo binário do arquivo, lido em chunks de 64 KB."""
    sha256 = hashlib.sha256()
    with open(caminho, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def _ler_amostra(caminho: Path, label: str) -> pd.DataFrame:
    """
    Lê apenas as primeiras 5 linhas para validação de estrutura.
    Levanta BatchValidacaoError se o arquivo não puder ser lido.
    """
    try:
        suf = caminho.suffix.lower()
        if suf in (".xlsx", ".xlsm"):
            return pd.read_excel(caminho, engine="openpyxl", nrows=5)
        if suf == ".xls":
            return pd.read_excel(caminho, nrows=5)
        return pd.read_csv(caminho, encoding="latin1", sep=";", nrows=5)
    except Exception as e:
        raise BatchValidacaoError(
            f"Não foi possível ler o arquivo de {label} '{caminho.name}': {e}"
        )


def _checar_colunas(
    df: pd.DataFrame,
    required: set,
    nome_arquivo: str,
    label: str,
) -> None:
    faltando = required - set(df.columns)
    if faltando:
        raise BatchValidacaoError(
            f"Arquivo de {label} '{nome_arquivo}' está faltando colunas obrigatórias: "
            f"{', '.join(sorted(faltando))}.\n"
            f"Colunas encontradas: {', '.join(df.columns.tolist())}"
        )
