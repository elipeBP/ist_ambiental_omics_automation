import requests
import time
import logging
from urllib.parse import quote
from typing import Dict, Optional

# Configuração do Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Limite da API do PubChem: estritamente não mais que 5 requisições por segundo
DELAY_REQUISICAO = 0.25

def buscar_dados_pubchem(nome_molecula: str) -> Optional[Dict]:
    """
    Consulta a API PUG REST do PubChem para buscar as propriedades de uma molécula pelo nome.
    
    Args:
        nome_molecula (str): Nome do composto (ex: 'Aspirin', 'Methanol').
        
    Returns:
        dict: Dicionário com CID, Fórmula e Peso, ou None se falhar.
    """
    # 1. Tratar o nome para formato de URL válida
    nome_limpo = quote(nome_molecula.strip())
    
    # 2. Endpoint estruturado (O mesmo que você desenhou no Excalidraw!)
    # Pedimos especificamente a Fórmula e o Peso Molecular para o JSON voltar mais leve e rápido
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{nome_limpo}/property/MolecularFormula,MolecularWeight/JSON"
    
    try:
        # Pausa obrigatória de segurança (Rate Limiting)
        time.sleep(DELAY_REQUISICAO)
        
        # Requisição HTTP com limite de tempo de 10 segundos
        response = requests.get(url, timeout=10)
        
        # Se o PubChem não conhecer a molécula, ele retorna o erro 404 (Not Found)
        if response.status_code == 404:
            logger.warning(f"Molécula não encontrada no PubChem: '{nome_molecula}'")
            return None
            
        # Dispara um erro se o servidor estiver fora do ar (Erro 500, etc.)
        response.raise_for_status()
        
        # 3. Parse do arquivo JSON de resposta
        dados = response.json()
        propriedades = dados.get('PropertyTable', {}).get('Properties', [])[0]
        
        cid = propriedades.get('CID')
        formula = propriedades.get('MolecularFormula')
        peso = propriedades.get('MolecularWeight')
        
        logger.info(f"✅ Sucesso: '{nome_molecula}' -> PubChem CID: {cid}")
        
        return {
            'nome_pesquisado': nome_molecula,
            'pubchem_cid': str(cid),
            'formula_quimica': formula,
            'peso_molecular': peso
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de conexão com a internet ao buscar '{nome_molecula}': {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado ao processar '{nome_molecula}': {e}")
        return None

# Bloco de testes isolados (Para rodar na sua máquina)
if __name__ == "__main__":
    print("Iniciando teste da API do PubChem...")
    
    # 1. Teste de Sucesso
    resultado_positivo = buscar_dados_pubchem("aspirin")
    print(f"\nResultado Aspirina:\n{resultado_positivo}")
    
    # 2. Teste de Tratamento de Erro (Molécula que não existe)
    resultado_negativo = buscar_dados_pubchem("molecula_falsa_12345")
    print(f"\nResultado Falso:\n{resultado_negativo}")