import os
import sys
import logging
import sqlite3
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


def _carregar_cache_moleculas() -> dict:
    """
    Lê dim_molecula completo para memória como {nome: dados_api}.

    Critério de "suficientemente enriquecida" (por API):
      - PubChem: pubchem_cid is not None  → skip PubChem neste batch
      - ChEBI  : chebi_id   is not None   → skip ChEBI neste batch

    Moléculas com campo nulo foram inseridas mas a API falhou anteriormente
    (erro de rede, molécula não indexada, etc.). Nesse caso a API é refeita
    no próximo batch — tratamento automático de falhas transitórias.

    Retorna {} se o banco ainda não existe (primeira execução).
    """
    from src.database.connection import DB_PATH

    if not DB_PATH.exists():
        return {}
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='dim_molecula'"
            )
            if not cur.fetchone():
                return {}
            cur.execute(
                "SELECT nome, pubchem_cid, formula, peso_molecular, chebi_id, classe_quimica "
                "FROM dim_molecula"
            )
            return {
                nome: {
                    "pubchem_cid":    cid,
                    "formula":        formula,
                    "peso_molecular": pm,
                    "chebi_id":       chebi_id,
                    "classe_quimica": classe or "Nao classificada",
                }
                for nome, cid, formula, pm, chebi_id, classe in cur.fetchall()
            }
    except Exception as exc:
        logger.warning(
            f"Cache de moléculas indisponível ({exc}) — todas as APIs serão consultadas."
        )
        return {}


def enriquecer_dados_laboratorio(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame consolidado da extração e produz o DataFrame de saída
    para o load, combinando:

        Campos laboratoriais (já presentes no arquivo, sem chamada de API):
            Score, Fragmentation Score, Mass Error (ppm), Isotope Similarity,
            Neutral mass (Da), Adducts

        Enriquecimento externo via APIs (com cache cross-batch e intra-batch):
            PubChem  → CID, fórmula química, peso molecular
            ChEBI    → CHEBI ID e classes ontológicas (busca por nome)

    Estratégia de cache:
        1. Carrega dim_molecula em memória antes do loop (cross-batch).
        2. Por molécula: se dados suficientes existem no cache → zero API calls.
        3. Após primeira consulta de cada molécula, atualiza cache em memória
           (intra-batch dedup: a mesma molécula nunca é consultada duas vezes
           na mesma execução do pipeline, mesmo que apareça em N sinais).

    Limite por sinais únicos configurável via OMICS_MAX_COMPOSTOS.
    """
    df_bruto = _aplicar_limite(df_bruto)

    total    = len(df_bruto)
    n_sinais = df_bruto["Compound"].nunique() if "Compound" in df_bruto.columns else "?"
    logger.info(f"Iniciando enriquecimento: {total} candidatos em {n_sinais} sinais...")

    # Cache cross-batch: carregado do banco uma vez por execução do pipeline
    cache = _carregar_cache_moleculas()
    logger.info(f"Cache cross-batch: {len(cache)} moléculas de execuções anteriores.")

    # Sets de controle intra-batch: garantem que cada molécula única é
    # consultada no máximo uma vez por execução, mesmo que apareça em vários sinais
    pubchem_processadas: set = set()
    chebi_processadas: set   = set()

    hits_pubchem = hits_chebi = miss_pubchem = miss_chebi = 0
    dados_enriquecidos = []

    for i, (index, row) in enumerate(df_bruto.iterrows(), start=1):
        nome_molecula  = str(row.get("Description", "")).strip()
        compound_code  = row.get("Compound")
        mz             = row.get("m/z")
        retention_time = row.get("Retention time (min)")

        if i % _LOG_A_CADA == 0 or i == 1 or i == total:
            logger.info(
                f"Progresso: {i}/{total} — sinal '{compound_code}' "
                f"[PubChem hits={hits_pubchem}/calls={miss_pubchem} | "
                f"ChEBI hits={hits_chebi}/calls={miss_chebi}]"
            )

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

        linha: dict = {
            "compound_code":      compound_code,
            "mz":                 mz,
            "retention_time":     retention_time,
            "description":        nome_molecula,
            "score_lab":          score_lab,
            "score_fragmentacao": score_fragmentacao,
            "mass_error_ppm":     mass_error_ppm,
            "score_isotopo":      score_isotopo,
            "neutral_mass_da":    neutral_mass_da,
            "adducts":            str(adducts).strip() if adducts and str(adducts) != "nan" else None,
            "pubchem_cid":        None,
            "formula":            None,
            "peso_molecular":     None,
            "chebi_id":           None,
            "classe_quimica":     "Nao classificada",
        }

        # ------------------------------------------------------------------
        # PubChem — fórmula, CID, peso molecular teórico
        #
        # Prioridade:
        #   1. Cross-batch cache hit: pubchem_cid já existe em dim_molecula
        #   2. Intra-batch hit: já consultado nesta execução (mesmo que sem dado)
        #   3. Cache miss: primeira vez que esta molécula aparece → chama API
        # ------------------------------------------------------------------
        c = cache.get(nome_molecula, {})
        if c.get("pubchem_cid") is not None:
            # Cache hit: dados completos do PubChem já disponíveis
            linha["pubchem_cid"]    = c["pubchem_cid"]
            linha["formula"]        = c.get("formula")
            linha["peso_molecular"] = c.get("peso_molecular")
            hits_pubchem += 1
        elif nome_molecula not in pubchem_processadas:
            # Cache miss: primeira ocorrência desta molécula → consulta PubChem
            resultado_pubchem = buscar_dados_pubchem(nome_molecula)
            miss_pubchem += 1
            if resultado_pubchem:
                linha["pubchem_cid"]    = resultado_pubchem.get("pubchem_cid")
                linha["formula"]        = resultado_pubchem.get("formula_quimica")
                linha["peso_molecular"] = resultado_pubchem.get("peso_molecular")
            # Atualiza cache em memória para ocorrências subsequentes neste batch
            cache.setdefault(nome_molecula, {}).update({
                "pubchem_cid":    linha["pubchem_cid"],
                "formula":        linha["formula"],
                "peso_molecular": linha["peso_molecular"],
            })
            pubchem_processadas.add(nome_molecula)
        else:
            # Intra-batch hit: já consultado nesta execução, reutiliza resultado
            c2 = cache[nome_molecula]
            linha["pubchem_cid"]    = c2.get("pubchem_cid")
            linha["formula"]        = c2.get("formula")
            linha["peso_molecular"] = c2.get("peso_molecular")
            hits_pubchem += 1

        # ------------------------------------------------------------------
        # ChEBI — classes ontológicas (busca por nome, sem ID hardcoded)
        #
        # Mesma prioridade de cache que o PubChem, avaliada de forma independente:
        # uma molécula pode ter cache hit no PubChem mas miss no ChEBI (se a
        # consulta ChEBI falhou na execução anterior por erro de rede).
        # ------------------------------------------------------------------
        c = cache.get(nome_molecula, {})
        if c.get("chebi_id") is not None:
            linha["chebi_id"]       = c["chebi_id"]
            linha["classe_quimica"] = c.get("classe_quimica", "Nao classificada")
            hits_chebi += 1
        elif nome_molecula not in chebi_processadas:
            resultado_chebi = buscar_ontologia_chebi(nome_molecula)
            miss_chebi += 1
            if resultado_chebi:
                linha["chebi_id"]       = resultado_chebi.get("chebi_id")
                linha["classe_quimica"] = resultado_chebi.get("classes_ontologicas", "Nao classificada")
            cache.setdefault(nome_molecula, {}).update({
                "chebi_id":       linha["chebi_id"],
                "classe_quimica": linha["classe_quimica"],
            })
            chebi_processadas.add(nome_molecula)
        else:
            c2 = cache[nome_molecula]
            linha["chebi_id"]       = c2.get("chebi_id")
            linha["classe_quimica"] = c2.get("classe_quimica", "Nao classificada")
            hits_chebi += 1

        dados_enriquecidos.append(linha)

    total_hits  = hits_pubchem + hits_chebi
    total_calls = miss_pubchem + miss_chebi
    logger.info(
        f"Enriquecimento concluído: {len(dados_enriquecidos)} candidatos | "
        f"PubChem: {hits_pubchem} hits / {miss_pubchem} chamadas | "
        f"ChEBI: {hits_chebi} hits / {miss_chebi} chamadas | "
        f"Total: {total_calls} chamadas reais, {total_hits} evitadas."
    )
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
