"""
Página: Relatórios
Geração e download de relatórios PDF das análises realizadas.
"""
import sys
from pathlib import Path

import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.reports.insights import computar_insights
from src.reports.narrative import gerar_narrativa
from src.reports.pdf_analitico import gerar_relatorio_analitico
from src.reports.pdf_executivo import gerar_relatorio_executivo
from src.reports.xlsx_export import gerar_exportacao_xlsx
from src.ui.utils import (
    carregar_cobertura_externa,
    carregar_ranking,
    carregar_ranking_batch,
    db_existe,
    listar_batches,
)

st.set_page_config(
    page_title="Relatórios | Omics ETL",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Relatórios")
st.caption(
    "Exportação de resultados para documentação, reuniões e revisão técnica "
    "| IST Ambiental / SENAI"
)
st.divider()

# ---------------------------------------------------------------------------
# Guarda de estado: banco inexistente
# ---------------------------------------------------------------------------
if not db_existe():
    st.info(
        "Nenhuma análise encontrada.  \n"
        "Use a página **📤 Nova Análise** para processar o primeiro experimento."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — seletor de análise
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _listar() -> list:
    return listar_batches()


batches_todos   = _listar()
batches_sucesso = [b for b in batches_todos if b["status"] == "sucesso"]

if not batches_sucesso:
    st.info("Nenhuma análise concluída com êxito ainda.")
    st.stop()

st.sidebar.header("Análise")
_ir_para   = st.session_state.pop("ir_para_batch", None)
_MAIS_REC  = None
opcoes_ids = [_MAIS_REC] + [b["id"] for b in batches_sucesso]


def _label(bid):
    if bid is None:
        sfx = f" (#{batches_sucesso[0]['id']})" if batches_sucesso else ""
        return f"Mais recente{sfx}"
    b = next((x for x in batches_sucesso if x["id"] == bid), None)
    if not b:
        return f"Análise #{bid}"
    data = (b["iniciado_em"] or "")[:10]
    nome = b["nome_ident"]
    if len(nome) > 22:
        nome = nome[:19] + "..."
    return f"#{bid} — {data} | {nome}"


idx_default = 0
if _ir_para and _ir_para in opcoes_ids:
    idx_default = opcoes_ids.index(_ir_para)

batch_sel = st.sidebar.selectbox(
    "Selecionar análise:",
    options=opcoes_ids,
    index=idx_default,
    format_func=_label,
    help="Análise cujo relatório será gerado.",
)
st.sidebar.divider()
st.sidebar.caption("Omics ETL · IST Ambiental / SENAI")

# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def _dados_recentes():
    return carregar_ranking()


@st.cache_data(ttl=300)
def _dados_batch(bid: int):
    return carregar_ranking_batch(bid)


df         = _dados_recentes() if batch_sel is None else _dados_batch(batch_sel)
batch_info = next((b for b in batches_sucesso if b["id"] == batch_sel), None) if batch_sel else None

if df.empty:
    st.warning(
        "Nenhum dado disponível para esta análise.  \n"
        "Verifique se o experimento foi concluído com sucesso."
    )
    st.stop()

batch_id_real = int(df["Batch ID"].iloc[0]) if "Batch ID" in df.columns else None

# ---------------------------------------------------------------------------
# Card de identificação da análise selecionada
# ---------------------------------------------------------------------------
if batch_info:
    d_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Análise**  \n#{batch_info['id']}")
        c2.markdown(f"**Processado em**  \n{d_raw}")
        c3.markdown(f"**Arquivo**  \n{batch_info.get('nome_ident', '—')}")
        _sinais = batch_info.get("total_sinais")
        _cands  = batch_info.get("total_candidatos")
        c4.markdown(
            f"**Dados**  \n"
            f"{_sinais if _sinais is not None else '—'} compostos · "
            f"{_cands if _cands is not None else '—'} candidatos"
        )
else:
    st.info("Análise mais recente com sucesso.")

st.divider()

# ---------------------------------------------------------------------------
# Seletor de tipo de relatório
# ---------------------------------------------------------------------------
st.subheader("Tipo de relatório")

_TIPO_RA   = "📊 Relatório Analítico"
_TIPO_RE   = "📋 Relatório Executivo"
_TIPO_XLSX = "📥 Exportação de Dados"

tipo_sel = st.radio(
    "Selecionar tipo:",
    options=[_TIPO_RA, _TIPO_RE, _TIPO_XLSX],
    horizontal=True,
    label_visibility="collapsed",
)

col_desc_l, col_desc_r = st.columns(2)

with col_desc_l:
    if tipo_sel == _TIPO_RA:
        with st.container(border=True):
            st.markdown("**📊 Relatório Analítico**")
            st.caption("Para químicos, especialistas e reuniões técnicas.")
            st.markdown(
                "- Badge de status + diagnóstico automático  \n"
                "- Tabela de compostos por prioridade de revisão  \n"
                "- Gráficos de scores e perfil químico  \n"
                "- Detalhamento de empates e nota metodológica  \n"
                "- Multi-página · linguagem técnica"
            )
    elif tipo_sel == _TIPO_RE:
        with st.container(border=True):
            st.markdown("**📋 Relatório Executivo**")
            st.caption("Para gestores, coordenadores e reuniões de gestão.")
            st.markdown(
                "- Status da análise em linguagem acessível  \n"
                "- Números resumidos: compostos, revisão, risco  \n"
                "- Perfil químico simplificado  \n"
                "- Recomendação de ação em destaque  \n"
                "- 1–2 páginas · sem scores técnicos"
            )
    else:
        with st.container(border=True):
            st.markdown("**📥 Exportação de Dados**")
            st.caption("Para análise, arquivo e integração com outros sistemas.")
            st.markdown(
                "- **6 abas:** Resumo · Resultado Final · Para Revisão · "
                "Dados Técnicos · Estatísticas · Metadados  \n"
                "- Uma linha por composto (Rank 1) com scores completos  \n"
                "- Lista de compostos para revisão com ação recomendada  \n"
                "- Tabela técnica com todos os candidatos e ranks  \n"
                "- Compatível com Excel e LibreOffice · gerado em memória"
            )

with col_desc_r:
    st.caption(
        "Formato A4  ·  Gerado em memória  ·  "
        "Pronto para impressão ou distribuição digital."
    )

st.divider()

# ---------------------------------------------------------------------------
# Geração do PDF — estado persistido por tipo de relatório
# ---------------------------------------------------------------------------

_STATE_KEY_BYTES    = "pdf_bytes_ra"
_STATE_KEY_BATCH    = "pdf_batch_id_ra"
_STATE_KEY_FILENAME = "pdf_filename_ra"
_STATE_KEY_BYTES_RE    = "pdf_bytes_re"
_STATE_KEY_BATCH_RE    = "pdf_batch_id_re"
_STATE_KEY_FILENAME_RE = "pdf_filename_re"
_STATE_KEY_BYTES_XLSX    = "xlsx_bytes"
_STATE_KEY_BATCH_XLSX    = "xlsx_batch_id"
_STATE_KEY_FILENAME_XLSX = "xlsx_filename"

# Invalida cache quando a análise muda
if st.session_state.get(_STATE_KEY_BATCH) != batch_id_real:
    st.session_state[_STATE_KEY_BYTES]    = None
    st.session_state[_STATE_KEY_BATCH]    = None
    st.session_state[_STATE_KEY_FILENAME] = None

if st.session_state.get(_STATE_KEY_BATCH_RE) != batch_id_real:
    st.session_state[_STATE_KEY_BYTES_RE]    = None
    st.session_state[_STATE_KEY_BATCH_RE]    = None
    st.session_state[_STATE_KEY_FILENAME_RE] = None

if st.session_state.get(_STATE_KEY_BATCH_XLSX) != batch_id_real:
    st.session_state[_STATE_KEY_BYTES_XLSX]    = None
    st.session_state[_STATE_KEY_BATCH_XLSX]    = None
    st.session_state[_STATE_KEY_FILENAME_XLSX] = None

st.subheader("Gerar relatório")
col_btn, col_status = st.columns([1, 2])

# ── Relatório Analítico ────────────────────────────────────────────────────
if tipo_sel == _TIPO_RA:
    with col_btn:
        _gerar_ra = st.button(
            "📄 Gerar Relatório Analítico",
            type="primary",
            use_container_width=True,
            help="Monta o PDF analítico completo em memória.",
        )

    if _gerar_ra:
        with st.spinner("Gerando Relatório Analítico..."):
            try:
                ins           = computar_insights(df)
                cobertura_ext = carregar_cobertura_externa(batch_id_real) if batch_id_real else {}
                pdf_bytes     = gerar_relatorio_analitico(ins, batch_info, cobertura_ext)
                bid_str       = f"batch{batch_id_real}" if batch_id_real else "recente"
                filename      = f"relatorio_analitico_{bid_str}.pdf"

                st.session_state[_STATE_KEY_BYTES]    = pdf_bytes
                st.session_state[_STATE_KEY_BATCH]    = batch_id_real
                st.session_state[_STATE_KEY_FILENAME] = filename
            except Exception as exc:
                st.error(f"Erro ao gerar o relatório:  \n`{exc}`")

    _pdf_bytes = st.session_state.get(_STATE_KEY_BYTES)
    _filename  = st.session_state.get(_STATE_KEY_FILENAME, "relatorio_analitico.pdf")

    if _pdf_bytes:
        with col_status:
            st.success(
                f"Relatório Analítico gerado — **{len(_pdf_bytes) / 1024:.0f} KB**  \n"
                "Clique abaixo para baixar."
            )
        st.download_button(
            label="⬇ Baixar Relatório Analítico",
            data=_pdf_bytes,
            file_name=_filename,
            mime="application/pdf",
            type="primary",
            use_container_width=False,
        )
        ins_prev = computar_insights(df)
        if ins_prev:
            st.divider()
            st.markdown("**Conteúdo incluído:**")
            _c1, _c2, _c3, _c4 = st.columns(4)
            _c1.metric("Compostos", ins_prev["n_compostos"])
            _c2.metric("Candidatos", ins_prev["n_candidatos_tot"])
            _c3.metric("Em empate", ins_prev["n_empates"] if ins_prev["_tem_empate"] else "—")
            _c4.metric("Score médio", f"{ins_prev['mean_pontuacao']:.1f}")

# ── Relatório Executivo ────────────────────────────────────────────────────
elif tipo_sel == _TIPO_RE:
    with col_btn:
        _gerar_re = st.button(
            "📋 Gerar Relatório Executivo",
            type="primary",
            use_container_width=True,
            help="Monta o PDF executivo (1–2 páginas) em memória.",
        )

    if _gerar_re:
        with st.spinner("Gerando Relatório Executivo..."):
            try:
                ins           = computar_insights(df)
                cobertura_ext = carregar_cobertura_externa(batch_id_real) if batch_id_real else {}
                pdf_bytes     = gerar_relatorio_executivo(ins, batch_info, cobertura_ext)
                bid_str       = f"batch{batch_id_real}" if batch_id_real else "recente"
                filename      = f"relatorio_executivo_{bid_str}.pdf"

                st.session_state[_STATE_KEY_BYTES_RE]    = pdf_bytes
                st.session_state[_STATE_KEY_BATCH_RE]    = batch_id_real
                st.session_state[_STATE_KEY_FILENAME_RE] = filename
            except Exception as exc:
                st.error(f"Erro ao gerar o relatório:  \n`{exc}`")

    _pdf_bytes_re = st.session_state.get(_STATE_KEY_BYTES_RE)
    _filename_re  = st.session_state.get(_STATE_KEY_FILENAME_RE, "relatorio_executivo.pdf")

    if _pdf_bytes_re:
        with col_status:
            st.success(
                f"Relatório Executivo gerado — **{len(_pdf_bytes_re) / 1024:.0f} KB**  \n"
                "Clique abaixo para baixar."
            )
        st.download_button(
            label="⬇ Baixar Relatório Executivo",
            data=_pdf_bytes_re,
            file_name=_filename_re,
            mime="application/pdf",
            type="primary",
            use_container_width=False,
        )

# ── Exportação XLSX ───────────────────────────────────────────────────────
else:
    with col_btn:
        _gerar_xlsx = st.button(
            "📥 Gerar Exportação XLSX",
            type="primary",
            use_container_width=True,
            help="Gera a planilha Excel consolidada com 6 abas em memória.",
        )

    if _gerar_xlsx:
        with st.spinner("Gerando Exportação XLSX..."):
            try:
                ins           = computar_insights(df)
                cobertura_ext = carregar_cobertura_externa(batch_id_real) if batch_id_real else {}
                nar           = gerar_narrativa(ins, cobertura_ext)
                xlsx_bytes    = gerar_exportacao_xlsx(ins, nar, batch_info, cobertura_ext)
                bid_str       = f"batch{batch_id_real}" if batch_id_real else "recente"
                filename      = f"resultado_omics_{bid_str}.xlsx"

                st.session_state[_STATE_KEY_BYTES_XLSX]    = xlsx_bytes
                st.session_state[_STATE_KEY_BATCH_XLSX]    = batch_id_real
                st.session_state[_STATE_KEY_FILENAME_XLSX] = filename
            except Exception as exc:
                st.error(f"Erro ao gerar a exportação:  \n`{exc}`")

    _xlsx_bytes = st.session_state.get(_STATE_KEY_BYTES_XLSX)
    _filename_x = st.session_state.get(_STATE_KEY_FILENAME_XLSX, "resultado_omics.xlsx")

    if _xlsx_bytes:
        with col_status:
            st.success(
                f"Exportação XLSX gerada — **{len(_xlsx_bytes) / 1024:.0f} KB**  \n"
                "Clique abaixo para baixar."
            )
        st.download_button(
            label="⬇ Baixar Exportação XLSX",
            data=_xlsx_bytes,
            file_name=_filename_x,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=False,
        )

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Omics ETL Pipeline · IST Ambiental / SENAI  ·  "
    "Os relatórios gerados são para uso interno e requerem validação do especialista analítico."
)
