"""
Página: Histórico de Execuções
Rastreabilidade completa de todos os batches processados pelo pipeline.
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.ui.utils import db_existe, listar_batches

st.set_page_config(
    page_title="Histórico | Omics ETL",
    page_icon="📋",
    layout="wide",
)

st.title("📋 Histórico de Execuções")
st.caption("Rastreabilidade completa de todos os processamentos realizados.")
st.divider()

if not db_existe():
    st.info("Banco de dados não encontrado. Execute `python main.py` para criar o banco.")
    st.stop()

# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _batches() -> list:
    return listar_batches()


batches = _batches()

if not batches:
    st.info(
        "Nenhuma execução registrada ainda.  \n"
        "Execute `python main.py` ou use a página **Carregar Dados** para processar um experimento."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Helpers de formatação
# ---------------------------------------------------------------------------
def _fmt_data(ts: str) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromisoformat(ts[:19]).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return ts[:16]


def _fmt_duracao(ini: str, fim: str) -> str:
    if not ini or not fim:
        return "—"
    try:
        t1   = datetime.fromisoformat(ini[:19])
        t2   = datetime.fromisoformat(fim[:19])
        secs = int((t2 - t1).total_seconds())
        if secs < 0:
            return "—"
        m, s = divmod(secs, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"
    except Exception:
        return "—"


STATUS_LABEL = {
    "sucesso":    "✅ Sucesso",
    "falha":      "❌ Falha",
    "executando": "⏳ Em execução",
    "pendente":   "⏸️ Pendente",
}

FONTE_LABEL = {
    "cli":           "Terminal",
    "upload_manual": "Upload UI",
    "polling":       "Automático",
    "legado":        "Legado (migrado)",
}

# ---------------------------------------------------------------------------
# Métricas resumidas
# ---------------------------------------------------------------------------
n_sucesso     = sum(1 for b in batches if b["status"] == "sucesso")
n_falha       = sum(1 for b in batches if b["status"] == "falha")
total_sinais  = sum((b["total_sinais"] or 0) for b in batches if b["status"] == "sucesso")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Execuções registradas", len(batches))
col2.metric("Com sucesso",           n_sucesso)
col3.metric("Com falha",             n_falha)
col4.metric("Sinais acumulados",     total_sinais if total_sinais else "—")

st.divider()

# ---------------------------------------------------------------------------
# Tabela principal
# ---------------------------------------------------------------------------
st.subheader("Todas as execuções")

rows = []
for b in batches:
    rows.append({
        "#":                      b["id"],
        "Data / Hora":            _fmt_data(b["iniciado_em"]),
        "Arquivo Identificação":  b["nome_ident"],
        "Sinais":                 b["total_sinais"]        if b["total_sinais"]        is not None else "—",
        "Candidatos":             b["total_candidatos"]    if b["total_candidatos"]    is not None else "—",
        "Novas moléculas (API)":  b["total_moleculas_api"] if b["total_moleculas_api"] is not None else "—",
        "Duração":                _fmt_duracao(b["iniciado_em"], b["concluido_em"]),
        "Status":                 STATUS_LABEL.get(b["status"], b["status"]),
        "Fonte":                  FONTE_LABEL.get(b["fonte"], b["fonte"]),
    })

df_hist = pd.DataFrame(rows)
st.dataframe(df_hist, hide_index=True, use_container_width=True)

# ---------------------------------------------------------------------------
# Detalhes de falhas (expanders por batch com erro)
# ---------------------------------------------------------------------------
falhas = [b for b in batches if b["status"] == "falha" and b.get("erro_mensagem")]
if falhas:
    st.divider()
    st.subheader("Detalhes das Falhas")
    for b in falhas:
        label = f"Batch #{b['id']} — {_fmt_data(b['iniciado_em'])} | {b['nome_ident']}"
        with st.expander(label):
            st.error(b["erro_mensagem"])

# ---------------------------------------------------------------------------
# Navegação para o Ranking de um batch específico
# ---------------------------------------------------------------------------
sucesso_list = [b for b in batches if b["status"] == "sucesso"]
if sucesso_list:
    st.divider()
    st.subheader("Abrir Ranking de um Experimento")

    opcoes = {
        b["id"]: f"Batch #{b['id']} — {_fmt_data(b['iniciado_em'])} | {b['nome_ident']}"
        for b in sucesso_list
    }

    batch_nav_id = st.selectbox(
        "Selecione o experimento:",
        options=list(opcoes.keys()),
        format_func=lambda bid: opcoes[bid],
    )

    if st.button("→ Ver Ranking", type="primary"):
        st.session_state["ir_para_batch"] = batch_nav_id
        st.switch_page("app.py")
