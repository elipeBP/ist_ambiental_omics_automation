import requests
import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

_UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"


def buscar_dados_uniprot(nome_molecula: str) -> Optional[Dict]:
    """
    Busca contexto biológico no UniProt pelo nome do composto/proteína.

    Mais relevante para dados proteômicos. Em dados metabolômicos, pode não encontrar
    resultados — isso é esperado e tratado como None (não é falha do pipeline).

    Args:
        nome_molecula: Nome do composto ou proteína.

    Returns:
        Dict com uniprot_id, funcao_biologica e organismo — ou None.
    """
    if not nome_molecula or not nome_molecula.strip():
        return None

    logger.info(f"Buscando UniProt para: '{nome_molecula}'")

    try:
        resp = requests.get(
            _UNIPROT_SEARCH_URL,
            params={
                "query":  nome_molecula.strip(),
                "format": "json",
                "size":   1,
                "fields": "accession,protein_name,organism_name,cc_function",
            },
            timeout=15,
        )

        if resp.status_code == 400:
            # Query inválida — tratar silenciosamente
            logger.warning(f"UniProt: query invalida para '{nome_molecula}'")
            return None

        resp.raise_for_status()
        dados = resp.json()

        resultados = dados.get("results", [])
        if not resultados:
            logger.info(f"UniProt: sem resultados para '{nome_molecula}' (esperado para metabolitos)")
            return None

        entrada     = resultados[0]
        uniprot_id  = entrada.get("primaryAccession", "")
        organismo   = entrada.get("organism", {}).get("scientificName", "")

        # Nome recomendado da proteína
        nome_prot = (
            entrada.get("proteinDescription", {})
            .get("recommendedName", {})
            .get("fullName", {})
            .get("value", "")
        )

        # Função biológica (comentário CC_FUNCTION)
        funcao_bio = None
        for comentario in entrada.get("comments", []):
            if comentario.get("commentType") == "FUNCTION":
                textos = comentario.get("texts", [])
                if textos:
                    funcao_bio = textos[0].get("value", "")
                    break

        logger.info(f"UniProt OK: {uniprot_id} ({organismo})")

        return {
            "uniprot_id":      uniprot_id,
            "nome_proteina":   nome_prot,
            "organismo":       organismo,
            "funcao_biologica": funcao_bio,
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"UniProt: erro de conexao para '{nome_molecula}': {e}")
        return None
    except Exception as e:
        logger.error(f"UniProt: erro inesperado para '{nome_molecula}': {e}")
        return None


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    for nome in ["insulin", "hemoglobin", "molecula_inexistente_xyz"]:
        print(f"\n--- {nome} ---")
        resultado = buscar_dados_uniprot(nome)
        print(resultado)
