import os
import sys
import logging
from pathlib import Path

import pandas as pd

# Encoding UTF-8 no terminal Windows (evita erro com caracteres especiais nos logs)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.api.pubchem import buscar_dados_pubchem
from src.api.chebi import buscar_ontologia_chebi

logger = logging.getLogger(__name__)

# Tamanho do lote exibido no log (não afeta o processamento, só o progresso)
_LOG_A_CADA = 50


def enriquecer_dados_laboratorio(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame consolidado da extração e enriquece cada composto
    com dados das APIs externas (PubChem → fórmula/peso/CID; ChEBI → ontologia).

    Fluxo por linha:
        1. PubChem  → CID, fórmula química, peso molecular
        2. ChEBI    → CHEBI ID e classes ontológicas (busca por nome)

    Limite configurável via variável de ambiente OMICS_MAX_COMPOSTOS.
    Exemplo: set OMICS_MAX_COMPOSTOS=50  (processa apenas os 50 primeiros)
    Sem a variável: processa o dataset completo.

    Retorna um DataFrame com todas as colunas necessárias para o load.
    """
    # Limite opcional para testes (evita esperar horas na primeira execução)
    max_compostos = os.environ.get("OMICS_MAX_COMPOSTOS")
    if max_compostos is not None:
        try:
            df_bruto = df_bruto.head(int(max_compostos))
            logger.info(f"OMICS_MAX_COMPOSTOS={max_compostos} — processando amostra limitada.")
        except ValueError:
            logger.warning(f"OMICS_MAX_COMPOSTOS='{max_compostos}' invalido, ignorando limite.")

    total = len(df_bruto)
    logger.info(f"Iniciando enriquecimento de {total} compostos...")

    dados_enriquecidos = []

    for i, (index, row) in enumerate(df_bruto.iterrows(), start=1):
        nome_molecula  = str(row.get("Description", "")).strip()
        compound_code  = row.get("Compound")
        mz             = row.get("m/z")
        retention_time = row.get("Retention time (min)")

        if i % _LOG_A_CADA == 0 or i == 1 or i == total:
            logger.info(f"Progresso: {i}/{total} — '{nome_molecula}'")

        # Estrutura base — preenchida progressivamente pelas APIs
        linha: dict = {
            "compound_code": compound_code,
            "description":   nome_molecula,
            "mz":            mz,
            "retention_time": retention_time,
            "pubchem_cid":   None,
            "formula":       None,
            "peso_molecular": None,
            "chebi_id":      None,
            "classe_quimica": "Nao classificada",
        }

        # --- PubChem ---
        resultado_pubchem = buscar_dados_pubchem(nome_molecula)
        if resultado_pubchem:
            linha["pubchem_cid"]    = resultado_pubchem.get("pubchem_cid")
            linha["formula"]        = resultado_pubchem.get("formula_quimica")
            linha["peso_molecular"] = resultado_pubchem.get("peso_molecular")

        # --- ChEBI (busca por nome — sem ID hardcoded) ---
        resultado_chebi = buscar_ontologia_chebi(nome_molecula)
        if resultado_chebi:
            linha["chebi_id"]      = resultado_chebi.get("chebi_id")
            linha["classe_quimica"] = resultado_chebi.get("classes_ontologicas", "Nao classificada")

        dados_enriquecidos.append(linha)

    logger.info(f"Enriquecimento concluido: {len(dados_enriquecidos)} registros processados.")
    return pd.DataFrame(dados_enriquecidos)


if __name__ == "__main__":
    from src.etl.extract import extrair_dados_brutos

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    RAW_DIR    = BASE_DIR / "data" / "raw"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")

    df_bruto = extrair_dados_brutos(RAW_DIR / nome_ident, RAW_DIR / nome_abund)
    if df_bruto is not None:
        df_pronto = enriquecer_dados_laboratorio(df_bruto)
        print("\nPre-visualizacao (primeiros 5 registros):")
        print(df_pronto.head().to_string())
