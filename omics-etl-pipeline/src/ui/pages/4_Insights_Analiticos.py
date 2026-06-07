"""
Página: Diagnóstico do Experimento
Painel de apoio à decisão analítica — IST Ambiental / SENAI.

Arquitetura v2:
  Zona 1 — Diagnóstico  : status global + parágrafo + ações recomendadas
  Zona 2 — O que fazer  : tabela de prioridades + detalhe de empates
  Zona 3 — Análise      : gráficos exploratórios (expander fechado)

Computação delegada para src.reports.insights.computar_insights(),
compartilhada com o gerador de relatórios PDF.
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.reports.insights import computar_insights
from src.reports.narrative import gerar_narrativa
from src.ui.utils import (
    carregar_cobertura_externa,
    carregar_ranking,
    carregar_ranking_batch,
    db_existe,
    listar_batches,
)

st.set_page_config(
    page_title="Diagnóstico do Experimento | Omics ETL",
    page_icon="🔬",
    layout="wide",
)

st.title("🔬 Diagnóstico do Experimento")
st.caption("Avaliação analítica automática dos resultados | IST Ambiental / SENAI")
st.divider()

# ---------------------------------------------------------------------------
# Guarda de estado
# ---------------------------------------------------------------------------
if not db_existe():
    st.info(
        "Nenhuma análise encontrada.  \n"
        "Use a página **📤 Nova Análise** para processar o primeiro experimento."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar
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
)
st.sidebar.divider()
st.sidebar.markdown("**Exportar**")
if st.sidebar.button(
    "📄 Gerar relatório PDF",
    use_container_width=True,
    help="Abre a página de relatórios com esta análise já selecionada",
):
    if batch_sel is not None:
        st.session_state["ir_para_batch"] = batch_sel
    st.switch_page("pages/5_Relatorios.py")
st.sidebar.divider()
st.sidebar.caption("Omics ETL · IST Ambiental / SENAI")

# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def _dados_recentes() -> pd.DataFrame:
    return carregar_ranking()


@st.cache_data(ttl=300)
def _dados_batch(bid: int) -> pd.DataFrame:
    return carregar_ranking_batch(bid)


df = _dados_recentes() if batch_sel is None else _dados_batch(batch_sel)

if df.empty:
    st.warning(
        "Nenhum dado disponível para esta análise.  \n"
        "Verifique se o experimento foi concluído com sucesso."
    )
    st.stop()

if "Rank" not in df.columns:
    st.error("Estrutura de dados incompatível. Recarregue a página.")
    st.stop()

batch_id_real = int(df["Batch ID"].iloc[0]) if "Batch ID" in df.columns else None

# ---------------------------------------------------------------------------
# Computação centralizada
# ---------------------------------------------------------------------------
ins = computar_insights(df)
if not ins:
    st.warning("Não foi possível calcular os indicadores analíticos.")
    st.stop()

score_col        = ins["score_col"]
_tem_empate      = ins["_tem_empate"]
_tem_criterio    = ins["_tem_criterio"]
rank1_df         = ins["rank1_df"]
rank1_unico      = ins["rank1_unico"]
compound_data    = ins["compound_data"]
n_compostos      = ins["n_compostos"]
mean_pontuacao   = ins["mean_pontuacao"]
n_empates        = ins["n_empates"]
pct_empates      = ins["pct_empates"]
criterio_counts  = ins["criterio_counts"]
criterio_dom     = ins["criterio_dom"]
criterio_dom_n   = ins["criterio_dom_n"]
n_resolvidos     = ins["n_resolvidos"]
n_nao_resolvidos = ins["n_nao_resolvidos"]
classes_classif  = ins["classes_classif"]
n_nc             = ins["n_nc"]
n_classif        = ins["n_classif"]
n_alta_conf      = ins["n_alta_conf"]

batch_info = (
    next((b for b in batches_sucesso if b["id"] == batch_sel), None)
    if batch_sel else None
)
if batch_info:
    d_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
    st.info(f"**Análise #{batch_info['id']}** — {d_raw} | {batch_info['nome_ident']}")

cobertura_ext: dict = {}
if batch_id_real is not None:
    cobertura_ext = carregar_cobertura_externa(batch_id_real)

pct_chebi = cobertura_ext.get("pct_chebi", 0)

# ---------------------------------------------------------------------------
# Narrativa — interpretação automática centralizada
# ---------------------------------------------------------------------------

nar           = gerar_narrativa(ins, cobertura_ext)
status_key    = nar["status"]
risco_label   = nar["risco_label"]
risco_desc    = nar["risco_desc"]
paragrafo_txt = nar["paragrafo"]
conclusao_txt = nar["conclusao"]
n_criticos    = nar["n_criticos"]
n_atencao     = nar["n_atencao"]
n_revisar     = nar["n_revisar"]
priority_df   = nar["priority_df"]
_emp_sinais   = ins.get("emp_sinais", frozenset())

# ═══════════════════════════════════════════════════════════════════════════
# ZONA 1 — DIAGNÓSTICO
# ═══════════════════════════════════════════════════════════════════════════

_STATUS_FN = {
    "conclusivo":   st.success,
    "parcial":      st.warning,
    "inconclusivo": st.error,
}
_STATUS_LBL = {
    "conclusivo":   "🟢  ANÁLISE CONCLUSIVA",
    "parcial":      "🟡  ANÁLISE PARCIALMENTE CONCLUSIVA",
    "inconclusivo": "🔴  ANÁLISE INCONCLUSIVA",
}

with st.container(border=True):
    _STATUS_FN[status_key](f"**{_STATUS_LBL[status_key]}**")
    st.markdown(paragrafo_txt)
    st.markdown(f"**▸** {conclusao_txt}")

st.markdown("")

# 3 indicadores de ação
c1, c2, c3 = st.columns(3)
with c1:
    with st.container(border=True):
        st.metric(
            "Revisão necessária",
            n_revisar,
            help=(
                f"{n_criticos} composto(s) em empate no Rank 1 e "
                f"{n_atencao} com confiança abaixo de 45."
            ),
        )
with c2:
    with st.container(border=True):
        st.metric(
            "Alta confiança",
            n_alta_conf,
            help="Compostos com score de identificação acima de 80.",
        )
with c3:
    with st.container(border=True):
        st.metric(
            "Risco analítico",
            risco_label,
            help=risco_desc,
        )

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# ZONA 2 — O QUE FAZER
# ═══════════════════════════════════════════════════════════════════════════

st.subheader("Compostos que exigem atenção")
st.caption(
    "Todos os compostos do experimento, ordenados por prioridade de revisão. "
    "🔴 Alta — empate no Rank 1, requer decisão do especialista. "
    "🟡 Média — baixa confiança de identificação. "
    "✅ OK — alta confiança."
)

st.dataframe(
    priority_df,
    hide_index=True,
    use_container_width=True,
    column_config={
        "Prioridade": st.column_config.TextColumn(
            "Prioridade",
            help="Nível de urgência para revisão manual deste composto",
        ),
        "Composto": st.column_config.TextColumn(
            "Composto",
            help="Código do sinal analítico atribuído pelo instrumento",
        ),
        "Confiança": st.column_config.ProgressColumn(
            "Confiança",
            help="Score de identificação do candidato Rank 1 (0–100)",
            min_value=0,
            max_value=100,
            format="%.1f",
        ),
        "Categoria": st.column_config.TextColumn(
            "Categoria química",
            help="Classificação amigável derivada dos dados ChEBI",
        ),
        "Situação": st.column_config.TextColumn(
            "Situação",
            help="Razão da prioridade atribuída a este composto",
        ),
        "Candidato mais provável": st.column_config.TextColumn(
            "Candidato mais provável",
            help="Molécula com Rank 1 para este composto",
        ),
    },
)

# Expander: candidatos empatados em detalhe
if n_criticos > 0 and _tem_empate:
    _score_emp_cols = [
        c for c in [
            "Candidato", score_col,
            "Score Fragmentacao", "Score Lab", "Isotope Similarity",
        ]
        if c in rank1_df.columns
    ]
    _rename_emp = {
        score_col: "Score",
        "Score Fragmentacao": "Fragmentação",
        "Isotope Similarity": "Isótopo",
    }
    with st.expander(
        f"Ver candidatos empatados em detalhe ({n_criticos} composto(s))",
        expanded=False,
    ):
        st.caption(
            "Candidatos que dividem o Rank 1 para cada composto em empate — "
            "indistinguíveis pelos critérios automáticos. "
            "A decisão do candidato definitivo requer avaliação do especialista."
        )
        for _sinal in sorted(_emp_sinais):
            _g = (
                rank1_df[rank1_df["Sinal"] == _sinal][_score_emp_cols]
                .rename(columns=_rename_emp)
            )
            st.markdown(f"**{_sinal}**")
            st.dataframe(_g, hide_index=True, use_container_width=True)

st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# ZONA 3 — ANÁLISE DETALHADA (expander fechado por padrão)
# ═══════════════════════════════════════════════════════════════════════════

with st.expander("Ver análise detalhada", expanded=False):

    # 1 — Mapa de confiança e ambiguidade (scatter)
    st.markdown("**Mapa de confiança e ambiguidade**")
    st.caption(
        "Cada ponto é um composto. Eixo horizontal: candidatos moleculares; "
        "eixo vertical: confiança de identificação. "
        "Superior esquerdo = identificação clara. "
        "Inferior direito = alta ambiguidade, revisão prioritária."
    )
    if len(compound_data) >= 2:
        _sc = compound_data.dropna(subset=["pontuacao_rank1"]).copy()
        _sc["pontuacao_rank1"] = _sc["pontuacao_rank1"].round(1)
        _h = (
            alt.Chart(pd.DataFrame({"y": [70.0]}))
            .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
            .encode(y="y:Q")
        )
        _v = (
            alt.Chart(pd.DataFrame({"x": [float(compound_data["n_candidatos"].quantile(0.75))]}))
            .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
            .encode(x="x:Q")
        )
        _scatter = (
            alt.Chart(_sc)
            .mark_circle(opacity=0.78)
            .encode(
                x=alt.X(
                    "n_candidatos:Q",
                    title="Candidatos moleculares",
                    scale=alt.Scale(zero=True),
                ),
                y=alt.Y(
                    "pontuacao_rank1:Q",
                    title="Confiança (Rank 1)",
                    scale=alt.Scale(domain=[0, 105]),
                ),
                size=alt.Size(
                    "n_candidatos:Q",
                    scale=alt.Scale(range=[50, 260]),
                    legend=None,
                ),
                color=alt.Color(
                    "pontuacao_rank1:Q",
                    scale=alt.Scale(scheme="blues", domain=[0, 100]),
                    legend=alt.Legend(title="Confiança", orient="right"),
                ),
                tooltip=[
                    alt.Tooltip("Sinal:N",                 title="Composto"),
                    alt.Tooltip("n_candidatos:Q",           title="Candidatos"),
                    alt.Tooltip("pontuacao_rank1:Q",        title="Confiança", format=".1f"),
                    alt.Tooltip("melhor_candidato_curto:N", title="Rank 1"),
                ],
            )
            .properties(height=300)
        )
        st.altair_chart(
            (_scatter + _h + _v).properties(height=300),
            use_container_width=True,
        )

    st.markdown("---")

    # 2 — Histograma de confiança
    st.markdown("**Confiança de identificação por composto (Rank 1)**")
    st.caption(
        "A linha vermelha pontilhada marca 80 — limiar de alta confiança. "
        "Distribuições deslocadas à esquerda indicam experimento com alta ambiguidade geral."
    )
    if not rank1_unico.empty and rank1_unico[score_col].notna().any():
        _sp = (
            rank1_unico[[score_col, "Sinal"]]
            .rename(columns={score_col: "Pontuação"})
            .copy()
        )
        _sp["Pontuação"] = pd.to_numeric(_sp["Pontuação"], errors="coerce")
        _sp = _sp.dropna(subset=["Pontuação"])
        if not _sp.empty:
            _hist = (
                alt.Chart(_sp)
                .mark_bar(
                    color="#4472c4",
                    opacity=0.85,
                    cornerRadiusTopLeft=2,
                    cornerRadiusTopRight=2,
                )
                .encode(
                    x=alt.X(
                        "Pontuação:Q",
                        bin=alt.Bin(step=10),
                        title="Confiança de identificação (Rank 1)",
                        axis=alt.Axis(values=list(range(0, 110, 10))),
                        scale=alt.Scale(domain=[0, 100]),
                    ),
                    y=alt.Y("count():Q", title="Compostos"),
                    tooltip=[
                        alt.Tooltip("Pontuação:Q", bin=alt.Bin(step=10), title="Faixa"),
                        alt.Tooltip("count():Q", title="Compostos"),
                    ],
                )
                .properties(height=200)
            )
            _l80 = (
                alt.Chart(pd.DataFrame({"v": [80.0]}))
                .mark_rule(color="#c0392b", strokeDash=[6, 3], opacity=0.65, size=1.5)
                .encode(x="v:Q")
            )
            st.altair_chart((_hist + _l80).properties(height=200), use_container_width=True)

    st.markdown("---")

    # 3 — Como as identificações foram resolvidas
    if _tem_criterio and not criterio_counts.empty:
        st.markdown("**Como as identificações foram resolvidas**")
        st.caption(
            "Distribuição dos critérios que determinaram o Rank 1. "
            "Fragmentação MS/MS é o critério de maior prioridade biológica (IST). "
            "Empate — decisão humana indica compostos que requerem avaliação manual."
        )
        _col_crit, _col_stat = st.columns([3, 1])
        with _col_crit:
            _bar_crit = (
                alt.Chart(criterio_counts)
                .mark_bar(opacity=0.88, cornerRadiusTopRight=2, cornerRadiusBottomRight=2)
                .encode(
                    y=alt.Y(
                        "label:N",
                        sort=None,
                        title=None,
                        axis=alt.Axis(labelLimit=200),
                    ),
                    x=alt.X("n:Q", title="Compostos"),
                    color=alt.Color("cor:N", scale=None, legend=None),
                    tooltip=[
                        alt.Tooltip("label:N", title="Critério"),
                        alt.Tooltip("n:Q",     title="Compostos"),
                    ],
                )
                .properties(height=max(180, len(criterio_counts) * 44))
            )
            st.altair_chart(_bar_crit, use_container_width=True)
        with _col_stat:
            _pct_auto = n_resolvidos / n_compostos * 100 if n_compostos else 0
            st.metric(
                "Identificados automaticamente",
                f"{n_resolvidos} ({_pct_auto:.0f}%)",
            )
            st.metric("Requerem revisão do especialista", n_nao_resolvidos)

    st.markdown("---")

    # 4 — Natureza química dos compostos
    if not classes_classif.empty:
        st.markdown("**Natureza química dos compostos identificados**")
        st.caption("Categorias químicas dos candidatos Rank 1 segundo PubChem / ChEBI.")
        _top = classes_classif.head(10).sort_values("Frequência", ascending=True)
        _bar_cl = (
            alt.Chart(_top)
            .mark_bar(
                color="#5a9e6f",
                opacity=0.82,
                cornerRadiusTopRight=2,
                cornerRadiusBottomRight=2,
            )
            .encode(
                y=alt.Y("Classe química:N", sort=None, title=None),
                x=alt.X("Frequência:Q", title="Compostos Rank 1"),
                tooltip=[
                    alt.Tooltip("Classe química:N", title="Categoria"),
                    alt.Tooltip("Frequência:Q",     title="Compostos"),
                ],
            )
            .properties(height=max(120, len(_top) * 32))
        )
        _col_cl, _col_cl_stats = st.columns([3, 1])
        with _col_cl:
            st.altair_chart(_bar_cl, use_container_width=True)
        with _col_cl_stats:
            st.metric("Classificados", f"{n_classif} / {n_compostos}")
            st.metric("Sem classificação", n_nc)
            if cobertura_ext:
                st.metric("Cobertura ChEBI",   f"{pct_chebi:.0f}%")
                st.metric(
                    "Cobertura PubChem",
                    f"{cobertura_ext.get('pct_pubchem', 0):.0f}%",
                )
    elif ins.get("_tem_classes", False):
        st.info(
            "Nenhum Rank 1 possui classificação química documentada.  \n"
            "Comum em análises de compostos emergentes ou de síntese."
        )

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption("Omics ETL Pipeline · IST Ambiental / SENAI")
