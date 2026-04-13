import requests
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_HMDB_SEARCH_URL = "https://hmdb.ca/metabolites/search"


def buscar_dados_hmdb(nome_molecula: str) -> Optional[Dict]:
    """
    Busca contexto metabólico no HMDB (Human Metabolome Database) pelo nome do composto.

    Retorna vias metabólicas, doenças associadas e localização biológica.
    Retorna None se o composto não for encontrado ou se a API estiver indisponível.

    Args:
        nome_molecula: Nome do composto (ex: 'Glucose', 'Aspirin').

    Returns:
        Dict com hmdb_id, via_metabolica, doenca_associada, localizacao_bio — ou None.
    """
    if not nome_molecula or not nome_molecula.strip():
        return None

    logger.info(f"Buscando HMDB para: '{nome_molecula}'")

    try:
        resp = requests.get(
            _HMDB_SEARCH_URL,
            params={"query": nome_molecula.strip(), "search_type": "metabolites"},
            headers={"Accept": "application/json"},
            timeout=15,
        )

        if resp.status_code == 404:
            logger.warning(f"HMDB: composto nao encontrado: '{nome_molecula}'")
            return None

        resp.raise_for_status()
        dados = resp.json()

        # A resposta do HMDB varia: pode ser lista ou dict com chave 'metabolites'
        metabolitos = dados if isinstance(dados, list) else dados.get("metabolites", [])

        if not metabolitos:
            logger.warning(f"HMDB: sem resultados para '{nome_molecula}'")
            return None

        primeiro = metabolitos[0]
        hmdb_id  = primeiro.get("accession", "")

        # Vias metabólicas
        vias = primeiro.get("biological_properties", {}).get("pathways", [])
        via_metabolica = ", ".join(v.get("name", "") for v in vias if v.get("name")) or None

        # Doenças associadas
        doencas = primeiro.get("diseases", [])
        doenca_associada = ", ".join(d.get("name", "") for d in doencas if d.get("name")) or None

        # Localização biológica (biospecimen)
        locais = primeiro.get("biological_properties", {}).get("biospecimen_locations", [])
        localizacao_bio = ", ".join(locais) if locais else None

        logger.info(f"HMDB OK: {hmdb_id} | vias: {via_metabolica}")

        return {
            "hmdb_id":          hmdb_id,
            "via_metabolica":   via_metabolica,
            "doenca_associada": doenca_associada,
            "localizacao_bio":  localizacao_bio,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"HMDB: erro de conexao para '{nome_molecula}': {e}")
        return None
    except Exception as e:
        logger.error(f"HMDB: erro inesperado para '{nome_molecula}': {e}")
        return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    for nome in ["Glucose", "Aspirin", "molecula_inexistente_xyz"]:
        print(f"\n--- {nome} ---")
        resultado = buscar_dados_hmdb(nome)
        print(resultado)
