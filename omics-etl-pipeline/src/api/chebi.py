import requests
import logging
from typing import Dict, Optional

# Configuração do Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def buscar_ontologia_chebi(chebi_id: str) -> Optional[Dict]:
    """
    Consulta a API OLS (Ontology Lookup Service) do EBI para buscar a ontologia de uma molécula.
    Esta é a API moderna e estável para dados ontológicos (JSON).
    
    Args:
        chebi_id (str): Código do ChEBI (ex: 'CHEBI:15365' para Aspirina).
        
    Returns:
        dict: Dicionário com o nome oficial e a lista de classes ontológicas, ou None.
    """
    # Garante o formato correto: 'CHEBI:15365'
    chebi_id_formatado = chebi_id.upper()
    if not chebi_id_formatado.startswith("CHEBI:"):
        chebi_id_formatado = f"CHEBI:{chebi_id_formatado}"
        
    logger.info(f"Consultando a API OLS do EBI para o ID: {chebi_id_formatado}...")
    
    # Endpoint oficial do OLS para buscar um termo exato
    url_termo = f"https://www.ebi.ac.uk/ols4/api/ontologies/chebi/terms?obo_id={chebi_id_formatado}"
    
    try:
        # 1. Busca os detalhes da molécula
        response = requests.get(url_termo, timeout=10)
        response.raise_for_status()
        dados = response.json()
        
        # Verifica se o banco de dados encontrou a molécula
        if '_embedded' not in dados or 'terms' not in dados['_embedded']:
            logger.warning(f"ID {chebi_id_formatado} não encontrado na base OLS.")
            return None
            
        termo = dados['_embedded']['terms'][0]
        nome_oficial = termo.get('label', 'Desconhecido')
        
        # 2. Busca a Ontologia (Quem são as classes "pai")
        # O OLS já nos dá um link direto (href) para consultar os pais dessa molécula!
        url_pais = termo.get('_links', {}).get('hierarchicalParents', {}).get('href')
        classes_superiores = []
        
        if url_pais:
            # Faz a segunda requisição rápida para pegar a família química
            res_pais = requests.get(url_pais, timeout=10)
            if res_pais.status_code == 200:
                dados_pais = res_pais.json()
                if '_embedded' in dados_pais and 'terms' in dados_pais['_embedded']:
                    for pai in dados_pais['_embedded']['terms']:
                        classes_superiores.append(pai.get('label'))
        
        # Junta todas as classes numa string separada por vírgula
        string_classes = ", ".join(classes_superiores) if classes_superiores else "Não classificada"
        
        logger.info(f"✅ Sucesso: {nome_oficial} pertence à classe: {string_classes}")
        
        return {
            'chebi_id': chebi_id_formatado,
            'nome_chebi': nome_oficial,
            'classes_ontologicas': string_classes
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de conexão com a API OLS para {chebi_id_formatado}: {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao processar o ChEBI {chebi_id_formatado}: {e}")
        return None

# Bloco de testes isolados
if __name__ == "__main__":
    print("Iniciando o teste da API REST OLS...")
    
    # Teste de Sucesso (Aspirina)
    resultado = buscar_ontologia_chebi("CHEBI:15365")
    print(f"\nResultado da Busca:\n{resultado}")