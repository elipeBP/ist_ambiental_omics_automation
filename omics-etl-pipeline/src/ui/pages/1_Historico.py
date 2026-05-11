"""
Página: Histórico de Análises
Registro de todos os experimentos processados pelo sistema.
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

st.title("📋 Histórico de Análises")
st.caption("Registro de todos os experimentos processados pelo sistema.")
st.divider()

if not db_existe():
    st.info("Nenhuma análise encontrada. Use a página **📤 Nova Análise** para processar o primeiro experimento.")
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
        "Nenhuma análise registrada ainda.  \n"
        "Use a página **📤 Nova Análise** para processar o primeiro experimento."
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
        if secs == 0:
            return "<1s"
        m, s = divmod(secs, 60)
        return f"{m}m {s:02d}s" if m else f"{s}s"
    except Exception:
        return "—"


STATUS_LABEL = {
    "sucesso":    "✅ Concluída",
    "falha":      "❌ Erro",
    "executando": "⏳ Em andamento",
    "pendente":   "⏸️ Aguardando",
}

FONTE_LABEL = {
    "cli":           "Linha de comando",
    "upload_manual": "Upload manual",
    "polling":       "Monitoramento automático",
    "legado":        "Dados anteriores",
}

# ---------------------------------------------------------------------------
# Métricas resumidas
# ---------------------------------------------------------------------------
n_sucesso    = sum(1 for b in batches if b["status"] == "sucesso")
n_falha      = sum(1 for b in batches if b["status"] == "falha")
total_sinais = sum((b["total_sinais"] or 0) for b in batches if b["status"] == "sucesso")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Análises realizadas",    len(batches))
col2.metric("Concluídas com êxito",   n_sucesso)
col3.metric("Com erro",               n_falha)
col4.metric("Compostos analisados",   total_sinais if total_sinais else "—")

st.divider()

# ---------------------------------------------------------------------------
# Tabela principal
# ---------------------------------------------------------------------------
st.subheader(f"Análises realizadas ({len(batches)})")

rows = []
for b in batches:
    rows.append({
        "#":                        b["id"],
        "Data / Hora":              _fmt_data(b["iniciado_em"]),
        "Arquivo de dados":         b["nome_ident"],
        "Compostos":                b["total_sinais"]        if b["total_sinais"]        is not None else "—",
        "Candidatos":               b["total_candidatos"]    if b["total_candidatos"]    is not None else "—",
        "Moléculas buscadas online": b["total_moleculas_api"] if b["total_moleculas_api"] is not None else "—",
        "Duração":                  _fmt_duracao(b["iniciado_em"], b["concluido_em"]),
        "Status":                   STATUS_LABEL.get(b["status"], b["status"]),
        "Origem":                   FONTE_LABEL.get(b["fonte"], b["fonte"]),
    })

df_hist = pd.DataFrame(rows)
st.dataframe(
    df_hist,
    hide_index=True,
    use_container_width=True,
    column_config={
        "#": st.column_config.NumberColumn("#", help="Identificador sequencial da análise"),
        "Compostos": st.column_config.NumberColumn(
            "Compostos",
            help="Número de sinais analíticos únicos processados nesta análise",
        ),
        "Candidatos": st.column_config.NumberColumn(
            "Candidatos",
            help="Total de candidatos moleculares identificados para todos os compostos desta análise",
        ),
        "Moléculas buscadas online": st.column_config.NumberColumn(
            "Moléculas buscadas online",
            help="Compostos consultados em bases de dados externas (PubChem, ChEBI) durante o processamento",
        ),
        "Origem": st.column_config.TextColumn(
            "Origem",
            help="Como esta análise foi iniciada: upload manual pela interface, linha de comando ou monitoramento automático",
        ),
    },
)

# ---------------------------------------------------------------------------
# Detalhes de erros
# ---------------------------------------------------------------------------
falhas = [b for b in batches if b["status"] == "falha" and b.get("erro_mensagem")]
if falhas:
    st.divider()
    st.subheader("Detalhes dos Erros")
    for b in falhas:
        label = f"Análise #{b['id']} — {_fmt_data(b['iniciado_em'])} | {b['nome_ident']}"
        with st.expander(label):
            st.error(b["erro_mensagem"])

# ---------------------------------------------------------------------------
# Navegação para os resultados de uma análise específica
# ---------------------------------------------------------------------------
sucesso_list = [b for b in batches if b["status"] == "sucesso"]
if sucesso_list:
    st.divider()
    st.subheader("Ver resultados de uma análise específica")

    opcoes = {
        b["id"]: f"Análise #{b['id']} — {_fmt_data(b['iniciado_em'])} | {b['nome_ident']}"
        for b in sucesso_list
    }

    batch_nav_id = st.selectbox(
        "Selecionar análise:",
        options=list(opcoes.keys()),
        format_func=lambda bid: opcoes[bid],
        help="Escolha uma análise para visualizar seus candidatos moleculares e rankings.",
    )

    if st.button("→ Ver candidatos", type="primary"):
        st.session_state["ir_para_batch"] = batch_nav_id
        st.switch_page("app.py")
