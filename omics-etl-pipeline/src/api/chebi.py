import requests
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

# Endpoint de busca textual no OLS4 — mais confiável do que forçar um ID específico
_OLS_SEARCH_URL = "https://www.ebi.ac.uk/ols4/api/search"
_OLS_TERM_URL   = "https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms"


def buscar_ontologia_chebi(nome_molecula: str) -> Optional[Dict]:
    """
    Busca a ontologia ChEBI pelo nome do composto via OLS4.

    Estratégia:
        1. Busca textual no OLS4 para obter o CHEBI ID a partir do nome.
        2. Com o CHEBI ID encontrado, busca os termos hierárquicos (classes pai).

    Args:
        nome_molecula: Nome do composto (ex: 'Aspirin', 'Glucose').

    Returns:
        Dict com chebi_id, nome_chebi e classes_ontologicas, ou None em caso de falha.
    """
    if not nome_molecula or not nome_molecula.strip():
        return None

    logger.info(f"Buscando ChEBI para: '{nome_molecula}'")

    # --- Passo 1: Busca textual para obter o CHEBI ID ---
    try:
        resp = requests.get(
            _OLS_SEARCH_URL,
            params={
                "q": nome_molecula.strip(),
                "ontology": "chebi",
                "type": "class",
                "rows": 1,
                "exact": "false",
            },
            timeout=10,
        )
        resp.raise_for_status()
        dados = resp.json()

        docs = dados.get("response", {}).get("docs", [])
        if not docs:
            logger.warning(f"ChEBI: nenhum resultado para '{nome_molecula}'")
            return None

        primeiro = docs[0]
        chebi_id      = primeiro.get("obo_id", "")        # ex: "CHEBI:15365"
        nome_oficial  = primeiro.get("label", nome_molecula)

        if not chebi_id.startswith("CHEBI:"):
            logger.warning(f"ChEBI: ID inesperado '{chebi_id}' para '{nome_molecula}'")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"ChEBI (busca): erro de conexão para '{nome_molecula}': {e}")
        return None
    except Exception as e:
        logger.error(f"ChEBI (busca): erro inesperado para '{nome_molecula}': {e}")
        return None

    # --- Passo 2: Busca dos termos hierárquicos (classes pai) ---
    classes_superiores = []
    try:
        resp_termo = requests.get(
            _OLS_TERM_URL,
            params={"obo_id": chebi_id},
            timeout=10,
        )
        if resp_termo.status_code == 200:
            dados_termo = resp_termo.json()
            termos = dados_termo.get("_embedded", {}).get("terms", [])
            if termos:
                url_pais = (
                    termos[0]
                    .get("_links", {})
                    .get("hierarchicalParents", {})
                    .get("href")
                )
                if url_pais:
                    resp_pais = requests.get(url_pais, timeout=10)
                    if resp_pais.status_code == 200:
                        pais = resp_pais.json().get("_embedded", {}).get("terms", [])
                        classes_superiores = [p.get("label") for p in pais if p.get("label")]

    except Exception as e:
        # Falha nos pais não invalida o resultado — retornamos o que temos
        logger.warning(f"ChEBI (hierarquia): erro ao buscar classes de '{chebi_id}': {e}")

    string_classes = ", ".join(classes_superiores) if classes_superiores else "Nao classificada"
    logger.info(f"ChEBI OK: {nome_oficial} ({chebi_id}) → {string_classes}")

    return {
        "chebi_id": chebi_id,
        "nome_chebi": nome_oficial,
        "classes_ontologicas": string_classes,
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    for nome in ["Aspirin", "Glucose", "molecula_inexistente_xyz"]:
        print(f"\n--- {nome} ---")
        resultado = buscar_ontologia_chebi(nome)
        print(resultado)
