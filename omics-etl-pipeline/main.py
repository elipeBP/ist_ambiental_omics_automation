import logging
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from src.etl.job import PipelineJob
from src.pipeline import executar_pipeline_com_job

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(module)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    BASE_DIR = Path(__file__).resolve().parent
    RAW_DIR  = BASE_DIR / "data" / "raw"

    nome_ident = os.environ.get("OMICS_IDENT_FILE", "IDENTIFICACAO.xlsx")
    nome_abund = os.environ.get("OMICS_ABUND_FILE", "ABUND.xlsx")

    job = PipelineJob(
        caminho_ident=RAW_DIR / nome_ident,
        caminho_abund=RAW_DIR / nome_abund,
        fonte="cli",
        nome_ident=nome_ident,
        nome_abund=nome_abund,
    )

    batch_id = executar_pipeline_com_job(job)

    if batch_id is not None:
        logger.info(f"Pipeline finalizado com sucesso. batch_id={batch_id}")
    else:
        logger.warning("Pipeline não concluído (ver logs acima para detalhes).")
