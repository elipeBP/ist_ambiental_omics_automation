"""
Gerenciamento do ciclo de vida de batches de execução do pipeline.

Cada execução do pipeline é registrada como um batch em `batch_execucao`.
Este módulo é a única interface com essa tabela — schema.py, pipeline.py
e ui/utils.py delegam aqui.
"""
import logging
import sqlite3
from typing import Optional

from src.database.connection import DB_PATH
from src.etl.validate import BatchDuplicadoError

logger = logging.getLogger(__name__)


def registrar_batch(
    hash_ident: str,
    hash_abund: str,
    nome_ident: str,
    nome_abund: str,
    fonte: str,
) -> int:
    """
    Cria uma nova linha em batch_execucao com status 'pendente' e retorna seu id.

    Regra de deduplicação:
        - Par de hashes com status='sucesso' → levanta BatchDuplicadoError.
        - Par com status='falha' ou 'executando' → permite reprocessamento
          (batch anterior crashado ou falhou; nova tentativa é legítima).

    Args:
        hash_ident / hash_abund: SHA-256 dos arquivos de entrada.
        nome_ident / nome_abund: nomes originais para exibição na UI.
        fonte: 'cli' | 'polling' | 'upload_manual'.

    Returns:
        ID do novo batch.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status FROM batch_execucao
            WHERE hash_ident = ? AND hash_abund = ?
            ORDER BY id DESC LIMIT 1
            """,
            (hash_ident, hash_abund),
        )
        existente = cur.fetchone()
        if existente and existente[1] == "sucesso":
            raise BatchDuplicadoError(
                f"Par de arquivos já processado com sucesso (batch_id={existente[0]}). "
                "Nenhuma ação necessária.",
                batch_id=existente[0],
            )

        cur.execute(
            """
            INSERT INTO batch_execucao
                (status, fonte, nome_ident, nome_abund, hash_ident, hash_abund)
            VALUES ('pendente', ?, ?, ?, ?, ?)
            """,
            (fonte, nome_ident, nome_abund, hash_ident, hash_abund),
        )
        conn.commit()
        batch_id = cur.lastrowid
        logger.info(f"Batch registrado: id={batch_id} fonte={fonte} ident={nome_ident}")
        return batch_id
    finally:
        conn.close()


def atualizar_status_batch(
    batch_id: int,
    status: str,
    total_sinais: Optional[int] = None,
    total_candidatos: Optional[int] = None,
    total_moleculas_api: Optional[int] = None,
    erro_mensagem: Optional[str] = None,
) -> None:
    """
    Transiciona o batch para um novo status e preenche campos de resultado.

    Em status terminal ('sucesso' ou 'falha'), grava concluido_em.
    Em status intermediário ('executando'), apenas atualiza o status.
    """
    campos_terminais = {"sucesso", "falha"}
    set_concluido = "concluido_em = CURRENT_TIMESTAMP," if status in campos_terminais else ""

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            f"""
            UPDATE batch_execucao SET
                status              = ?,
                {set_concluido}
                total_sinais        = COALESCE(?, total_sinais),
                total_candidatos    = COALESCE(?, total_candidatos),
                total_moleculas_api = COALESCE(?, total_moleculas_api),
                erro_mensagem       = COALESCE(?, erro_mensagem)
            WHERE id = ?
            """,
            (status, total_sinais, total_candidatos, total_moleculas_api,
             erro_mensagem, batch_id),
        )
        conn.commit()
        logger.info(f"Batch {batch_id} → status={status}")
    finally:
        conn.close()


def marcar_batches_zumbis(timeout_minutos: int = 30) -> None:
    """
    Marca como 'falha' qualquer batch que ficou preso em 'executando'.

    Um batch fica zumbi quando o processo Python é encerrado abruptamente
    no meio da execução. Chamado no início de cada pipeline run para limpar
    o estado antes de registrar um novo batch.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE batch_execucao SET
                status        = 'falha',
                concluido_em  = CURRENT_TIMESTAMP,
                erro_mensagem = 'Execução interrompida inesperadamente (processo encerrado)'
            WHERE status = 'executando'
              AND iniciado_em < datetime('now', '-{timeout_minutos} minutes')
            """,
        )
        if cur.rowcount:
            logger.warning(f"Marcados {cur.rowcount} batch(es) zumbi(s) como 'falha'.")
        conn.commit()
    finally:
        conn.close()


def listar_batches() -> list:
    """
    Retorna todos os batches ordenados do mais recente para o mais antigo.
    Usado pela UI de histórico.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, status, fonte, nome_ident, nome_abund,
                   iniciado_em, concluido_em,
                   total_sinais, total_candidatos, total_moleculas_api,
                   erro_mensagem
            FROM batch_execucao
            ORDER BY id DESC
            """
        )
        colunas = [d[0] for d in cur.description]
        return [dict(zip(colunas, row)) for row in cur.fetchall()]
    except sqlite3.OperationalError:
        return []   # tabela ainda não existe (banco vazio)
    finally:
        conn.close()
