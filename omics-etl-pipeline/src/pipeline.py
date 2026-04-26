"""
Orquestrador unificado do pipeline ETL.

Este módulo é o único entry point do ETL — chamado por main.py (CLI),
pela UI de upload (Streamlit) e pelo watcher de polling.
Nenhuma dessas fontes conhece os detalhes do ETL; todas passam um PipelineJob.
"""
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.database.schema import criar_tabelas
from src.database.batch import (
    registrar_batch,
    atualizar_status_batch,
    marcar_batches_zumbis,
)
from src.etl.validate import (
    validar_arquivos_entrada,
    BatchValidacaoError,
    BatchDuplicadoError,
)
from src.etl.job import PipelineJob
from src.etl.extract import extrair_dados_brutos
from src.etl.transform import enriquecer_dados_laboratorio
from src.etl.load import carregar_dados_no_banco

logger = logging.getLogger(__name__)


def executar_pipeline_com_job(job: PipelineJob) -> "int | None":
    """
    Executa o pipeline completo para um PipelineJob.

    Fluxo:
        0. Schema + limpeza de zumbis
        1. Validação dos arquivos de entrada
        2. Registro do batch + verificação de duplicata
        3. Extract → Transform → Load
        4. Atualização do status final

    Retorna:
        batch_id (int) em caso de sucesso.
        None em caso de duplicata, validação inválida ou falha.
    """
    # 0. Garante schema e limpa batches presos
    criar_tabelas()
    marcar_batches_zumbis()

    # 1. Validação antecipada dos arquivos
    try:
        validados = validar_arquivos_entrada(job.caminho_ident, job.caminho_abund)
    except BatchValidacaoError as e:
        logger.error(f"Validação falhou: {e}")
        return None

    # 2. Registro do batch (inclui verificação de duplicata por hash)
    try:
        batch_id = registrar_batch(
            hash_ident=validados.hash_ident,
            hash_abund=validados.hash_abund,
            nome_ident=job.nome_ident,
            nome_abund=job.nome_abund,
            fonte=job.fonte,
        )
    except BatchDuplicadoError as e:
        logger.info(f"Batch ignorado (duplicado): {e}")
        return None

    atualizar_status_batch(batch_id, "executando")

    try:
        # 3a. Extract
        logger.info(f"[Batch {batch_id}] Iniciando extração...")
        df_bruto = extrair_dados_brutos(job.caminho_ident, job.caminho_abund)
        if df_bruto is None or df_bruto.empty:
            raise RuntimeError("Extração retornou DataFrame vazio após validação bem-sucedida.")

        # 3b. Transform
        logger.info(f"[Batch {batch_id}] Iniciando enriquecimento via APIs...")
        df_transformado = enriquecer_dados_laboratorio(df_bruto)
        if df_transformado is None or df_transformado.empty:
            raise RuntimeError("Transformação retornou DataFrame vazio.")

        # 3c. Load
        logger.info(f"[Batch {batch_id}] Iniciando carga no banco...")
        sucesso = carregar_dados_no_banco(df_transformado)
        if not sucesso:
            raise RuntimeError("Carga retornou falha (ver logs anteriores para detalhes).")

        # Estatísticas para o registro de auditoria
        total_sinais = int(df_transformado["compound_code"].nunique())
        total_candidatos = len(df_transformado)

        atualizar_status_batch(
            batch_id,
            "sucesso",
            total_sinais=total_sinais,
            total_candidatos=total_candidatos,
        )
        logger.info(
            f"[Batch {batch_id}] Pipeline concluído: "
            f"{total_sinais} sinais, {total_candidatos} candidatos."
        )
        return batch_id

    except Exception as e:
        logger.error(f"[Batch {batch_id}] Pipeline falhou: {e}")
        atualizar_status_batch(batch_id, "falha", erro_mensagem=str(e))
        return None
