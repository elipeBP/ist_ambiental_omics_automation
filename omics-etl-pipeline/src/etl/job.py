from dataclasses import dataclass
from pathlib import Path


@dataclass
class PipelineJob:
    """
    Descreve uma requisição de execução do pipeline.
    O core do ETL recebe apenas este objeto — não conhece a fonte de ingestão.
    """
    caminho_ident: Path
    caminho_abund: Path
    fonte: str        # 'cli' | 'polling' | 'upload_manual'
    nome_ident: str   # nome original do arquivo (para trilha de auditoria)
    nome_abund: str
