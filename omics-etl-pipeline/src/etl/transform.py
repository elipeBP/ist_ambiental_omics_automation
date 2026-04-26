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

# Frequência de log de progresso (a cada N linhas processadas)
_LOG_A_CADA = 100


def _aplicar_limite(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aplica o limite de OMICS_MAX_COMPOSTOS ao DataFrame, filtrando por
    sinais únicos (Compound) — não por número de linhas.

    Isso garante que todos os candidatos de um sinal são processados juntos,
    preservando a semântica N:N do modelo.

    Exemplo: OMICS_MAX_COMPOSTOS=5 processa os 5 primeiros sinais únicos
    com TODOS os seus candidatos (que podem ser centenas de linhas).
    """
    valor = os.environ.get("OMICS_MAX_COMPOSTOS")
    if valor is None:
        return df

    try:
        n = int(valor)
    except ValueError:
        logger.warning(f"OMICS_MAX_COMPOSTOS='{valor}' invalido, ignorando limite.")
        return df

    compostos_unicos = df["Compound"].unique()[:n]
    df_limitado = df[df["Compound"].isin(compostos_unicos)].copy()

    logger.info(
        f"OMICS_MAX_COMPOSTOS={n} — {len(compostos_unicos)} sinais, "
        f"{len(df_limitado)} candidatos no total."
    )
    return df_limitado


def enriquecer_dados_laboratorio(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame consolidado da extração e produz o DataFrame de saída
    para o load, combinando:

        Campos laboratoriais (já presentes no arquivo, sem chamada de API):
            Score, Fragmentation Score, Mass Error (ppm), Isotope Similarity,
            Neutral mass (Da), Adducts

        Enriquecimento externo via APIs:
            PubChem  → CID, fórmula química, peso molecular
            ChEBI    → CHEBI ID e classes ontológicas (busca por nome)

    Limite por sinais únicos configurável via OMICS_MAX_COMPOSTOS.
    """
    df_bruto = _aplicar_limite(df_bruto)

    total = len(df_bruto)
    n_sinais = df_bruto["Compound"].nunique() if "Compound" in df_bruto.columns else "?"
    logger.info(f"Iniciando enriquecimento: {total} candidatos em {n_sinais} sinais...")

    dados_enriquecidos = []

    for i, (index, row) in enumerate(df_bruto.iterrows(), start=1):
        nome_molecula  = str(row.get("Description", "")).strip()
        compound_code  = row.get("Compound")
        mz             = row.get("m/z")
        retention_time = row.get("Retention time (min)")

        if i % _LOG_A_CADA == 0 or i == 1 or i == total:
            logger.info(f"Progresso: {i}/{total} — sinal '{compound_code}'")

        # ------------------------------------------------------------------
        # Campos laboratoriais — capturados diretamente do dataset
        # (gerados pelo software do equipamento, já disponíveis sem API)
        # ------------------------------------------------------------------
        score_lab          = row.get("Score")
        score_fragmentacao = row.get("Fragmentation Score")
        mass_error_ppm     = row.get("Mass Error (ppm)")
        score_isotopo      = row.get("Isotope Similarity")
        neutral_mass_da    = row.get("Neutral mass (Da)")
        adducts            = row.get("Adducts")

        # Estrutura base da linha enriquecida
        linha: dict = {
            # Identificação do sinal
            "compound_code":      compound_code,
            "mz":                 mz,
            "retention_time":     retention_time,
            # Identificação do candidato
            "description":        nome_molecula,
            # Campos laboratoriais (dataset)
            "score_lab":          score_lab,
            "score_fragmentacao": score_fragmentacao,
            "mass_error_ppm":     mass_error_ppm,
            "score_isotopo":      score_isotopo,
            "neutral_mass_da":    neutral_mass_da,
            "adducts":            str(adducts).strip() if adducts and str(adducts) != "nan" else None,
            # Campos de enriquecimento via API (preenchidos abaixo)
            "pubchem_cid":        None,
            "formula":            None,
            "peso_molecular":     None,
            "chebi_id":           None,
            "classe_quimica":     "Nao classificada",
        }

        # ------------------------------------------------------------------
        # PubChem — fórmula, CID, peso molecular teórico
        # ------------------------------------------------------------------
        resultado_pubchem = buscar_dados_pubchem(nome_molecula)
        if resultado_pubchem:
            linha["pubchem_cid"]    = resultado_pubchem.get("pubchem_cid")
            linha["formula"]        = resultado_pubchem.get("formula_quimica")
            linha["peso_molecular"] = resultado_pubchem.get("peso_molecular")

        # ------------------------------------------------------------------
        # ChEBI — classes ontológicas (busca por nome, sem ID hardcoded)
        # ------------------------------------------------------------------
        resultado_chebi = buscar_ontologia_chebi(nome_molecula)
        if resultado_chebi:
            linha["chebi_id"]       = resultado_chebi.get("chebi_id")
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
        colunas_lab = [
            "compound_code", "description", "score_lab", "score_fragmentacao",
            "mass_error_ppm", "score_isotopo", "neutral_mass_da", "adducts"
        ]
        print(df_pronto[colunas_lab].head().to_string())
