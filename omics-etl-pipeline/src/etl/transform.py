import os
import pandas as pd
import logging
import sys
from pathlib import Path

# Evita UnicodeEncodeError no print (Windows/cp1252) com emojis nos logs
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Configuração para o Python encontrar as nossas pastas 'src'
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.etl.extract import extrair_dados_brutos
from src.api.pubchem import buscar_dados_pubchem
from src.api.chebi import buscar_ontologia_chebi

# Configuração do Logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def enriquecer_dados_laboratorio(df_bruto: pd.DataFrame) -> pd.DataFrame:
    """
    Recebe o DataFrame com os dados brutos, itera sobre as moléculas e 
    enriquece com dados do PubChem e ChEBI.
    """
    logger.info(f"🚀 Iniciando a Transformação e Enriquecimento de {len(df_bruto)} moléculas...")
    
    # Lista para armazenar as linhas processadas (que vão virar o DataFrame final)
    dados_enriquecidos = []
    
    # Vamos processar apenas as primeiras 3 moléculas para teste (para não esperar muito tempo agora)
    # No pipeline real, tiramos esse [:3]
    df_teste = df_bruto.head(3)
    
    for index, row in df_teste.iterrows():
        nome_molecula = str(row.get('Description')).strip()
        codigo_equipamento = row.get('Compound')
        mz = row.get('m/z')
        retention_time = row.get('Retention time (min)')
        
        logger.info(f"⏳ Processando [{index+1}/{len(df_teste)}]: {nome_molecula}")
        
        # 1. Dados Básicos que já vieram do equipamento
        linha_enriquecida = {
            'compound_code': codigo_equipamento,
            'description': nome_molecula,
            'mz': mz,
            'retention_time': retention_time,
            'pubchem_cid': None,
            'formula': None,
            'chebi_id': None,
            'classe_quimica': 'Não classificada'
        }
        
        # 2. Bate no PubChem para pegar Fórmula, Peso e CID
        resultado_pubchem = buscar_dados_pubchem(nome_molecula)
        
        if resultado_pubchem:
            linha_enriquecida['pubchem_cid'] = resultado_pubchem['pubchem_cid']
            linha_enriquecida['formula'] = resultado_pubchem['formula_quimica']
            
            # ATENÇÃO: Na vida real, usaríamos o CID para buscar o Cross-Reference do ChEBI ID.
            # Como teste, se for Aspirina, a gente injeta o ID que sabemos para ver o fluxo.
            # Em moléculas normais do IST, teríamos uma função de conversão aqui.
            chebi_teste_id = "CHEBI:15365" if "aspirin" in nome_molecula.lower() else "CHEBI:17584" # 17584 = Vitamina C
            
            # 3. Bate no ChEBI OLS para pegar a Ontologia
            resultado_chebi = buscar_ontologia_chebi(chebi_teste_id)
            
            if resultado_chebi:
                linha_enriquecida['chebi_id'] = resultado_chebi['chebi_id']
                linha_enriquecida['classe_quimica'] = resultado_chebi['classes_ontologicas']
                
        # Adiciona a linha pronta à nossa lista final"
        dados_enriquecidos.append(linha_enriquecida)
        
    logger.info("✅ Transformação concluída com sucesso!")
    
    # Converte a lista de dicionários de volta para um DataFrame do Pandas limpinho
    df_final = pd.DataFrame(dados_enriquecidos)
    return df_final

if __name__ == "__main__":
    # Caminhos dos arquivos brutos (mesmas variáveis que em extract.py)
    RAW_DIR = BASE_DIR / "data" / "raw"
    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")
    ARQUIVO_IDENT = RAW_DIR / nome_ident
    ARQUIVO_ABUND = RAW_DIR / nome_abund
    
    # 1. EXTRAIR
    df_bruto = extrair_dados_brutos(ARQUIVO_IDENT, ARQUIVO_ABUND)
    
    if df_bruto is not None:
        # 2. TRANSFORMAR E ENRIQUECER
        df_pronto_para_banco = enriquecer_dados_laboratorio(df_bruto)
        
        print("\n[VISUALIZACAO] DataFrame final (pronto para SQLite/PostgreSQL):")
        print(df_pronto_para_banco.to_string())