"""
Página: Insights Analíticos
Exploração visual dos resultados do experimento — apoio à interpretação analítica.

A computação de métricas é delegada para src.reports.insights.computar_insights(),
compartilhada com o gerador de relatórios PDF.
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.reports.insights import CRITERIO_COLOR, CRITERIO_LABEL, CRITERIO_ORDER, computar_insights
from src.ui.utils import (
    carregar_cobertura_externa,
    carregar_ranking,
    carregar_ranking_batch,
    db_existe,
    listar_batches,
)

st.set_page_config(
    page_title="Insights Analíticos | Omics ETL",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Insights Analíticos")
st.caption(
    "Indicadores de apoio à interpretação analítica | IST Ambiental / SENAI"
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
    help="Selecione um experimento para visualizar seus indicadores analíticos.",
)
st.sidebar.divider()

# Atalho para geração de relatório PDF
st.sidebar.markdown("**Exportar**")
if st.sidebar.button("📄 Gerar relatório PDF", use_container_width=True,
                     help="Abre a página de relatórios com esta análise já selecionada"):
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

# Batch ID real (para queries adicionais — ChEBI, PubChem; e para o atalho PDF)
batch_id_real = int(df["Batch ID"].iloc[0]) if "Batch ID" in df.columns else None

# ---------------------------------------------------------------------------
# Computação centralizada (compartilhada com o PDF builder)
# ---------------------------------------------------------------------------
ins = computar_insights(df)
if not ins:
    st.warning("Não foi possível calcular os indicadores analíticos.")
    st.stop()

# Desempacota para conveniência — mesma interface de antes
score_col        = ins["score_col"]
_tem_empate      = ins["_tem_empate"]
_tem_criterio    = ins["_tem_criterio"]
_tem_classes     = ins["_tem_classes"]
rank1_df         = ins["rank1_df"]
rank1_unico      = ins["rank1_unico"]
compound_data    = ins["compound_data"]
n_compostos      = ins["n_compostos"]
n_candidatos_tot = ins["n_candidatos_tot"]
mean_pontuacao   = ins["mean_pontuacao"]
mean_cand_comp   = ins["mean_cand_comp"]
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
pct_classif      = ins["pct_classif"]
_insights        = ins["insights"]

# ---------------------------------------------------------------------------
# Banner da análise histórica selecionada
# ---------------------------------------------------------------------------
batch_info = next((b for b in batches_sucesso if b["id"] == batch_sel), None) if batch_sel else None
if batch_info:
    d_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
    st.info(f"**Análise #{batch_info['id']}** — {d_raw} | {batch_info['nome_ident']}")

# Cobertura de bases externas (ChEBI / PubChem)
cobertura_ext: dict = {}
if batch_id_real is not None:
    cobertura_ext = carregar_cobertura_externa(batch_id_real)

# ===========================================================================
# BLOCO 1 — Resumo da análise
# ===========================================================================
st.subheader("Resumo da análise")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    "Compostos detectados",
    n_compostos,
    help="Sinais analíticos únicos identificados pelo instrumento neste experimento",
)
m2.metric(
    "Total de candidatos",
    n_candidatos_tot,
    help="Soma de todos os candidatos moleculares sugeridos para todos os compostos",
)
m3.metric(
    "Score médio (Rank 1)",
    f"{mean_pontuacao:.1f}",
    help="Score médio de identificação dos candidatos mais prováveis — escala 0 a 100",
)
m4.metric(
    "Compostos em empate",
    f"{n_empates} ({pct_empates:.0f}%)" if _tem_empate else "—",
    help=(
        "Compostos com dois ou mais candidatos indistinguíveis automaticamente no Rank 1. "
        "Requerem decisão do especialista."
    ),
)
m5.metric(
    "Candidatos por composto",
    f"{mean_cand_comp:.1f}",
    help="Média de candidatos moleculares por composto — valores altos indicam maior ambiguidade",
)

st.divider()

# ===========================================================================
# BLOCO 5 — Leitura rápida / Insights automáticos
# ===========================================================================
st.subheader("Leitura rápida do experimento")

with st.container(border=True):
    for _tipo, _texto in _insights:
        getattr(st, _tipo)(_texto)

st.divider()

# ===========================================================================
# BLOCO 2 — Ranking de sinais
# ===========================================================================
st.subheader("Ranking de sinais")
st.caption("Compostos organizados por diferentes critérios analíticos. Use as abas para explorar.")

tab_conf, tab_ambig, tab_cands, tab_empate = st.tabs([
    "Mais confiáveis",
    "Menos confiáveis",
    "Mais candidatos",
    "Em empate",
])

_TOP  = 15
_base = compound_data.copy()
_base["pontuacao_rank1"] = pd.to_numeric(_base["pontuacao_rank1"], errors="coerce")

# Enriquece _base com critério de desempate (label legível)
if _tem_criterio:
    _crit_sinal = rank1_unico[["Sinal", "Criterio Desempate"]].drop_duplicates("Sinal")
    _base = _base.merge(_crit_sinal, on="Sinal", how="left")
    _base["Criterio Desempate"] = _base["Criterio Desempate"].map(
        lambda x: CRITERIO_LABEL.get(str(x), str(x)) if pd.notna(x) else "—"
    )

_COLS_SRC_BASE = ["Sinal", "pontuacao_rank1", "n_candidatos", "melhor_candidato_curto"]
_COLS_DST_BASE = ["Composto", "Score Rank 1", "N° candidatos", "Candidato mais provável"]
if _tem_criterio and "Criterio Desempate" in _base.columns:
    _COLS_SRC = _COLS_SRC_BASE + ["Criterio Desempate"]
    _COLS_DST = _COLS_DST_BASE + ["Critério de desempate"]
else:
    _COLS_SRC, _COLS_DST = _COLS_SRC_BASE, _COLS_DST_BASE


def _tabela(df_tab: pd.DataFrame, cols_src: list, cols_dst: list) -> pd.DataFrame:
    avail_src = [c for c in cols_src if c in df_tab.columns]
    avail_dst = [cols_dst[i] for i, c in enumerate(cols_src) if c in df_tab.columns]
    out = df_tab[avail_src].copy()
    out.columns = avail_dst
    if "Score Rank 1" in out.columns:
        out["Score Rank 1"] = pd.to_numeric(out["Score Rank 1"], errors="coerce").round(1)
    return out.reset_index(drop=True)


with tab_conf:
    st.caption("Compostos com maior score no Rank 1 — melhor correspondência espectral.")
    _top = _base.dropna(subset=["pontuacao_rank1"]).nlargest(_TOP, "pontuacao_rank1")
    st.dataframe(_tabela(_top, _COLS_SRC, _COLS_DST), hide_index=True, use_container_width=True)

with tab_ambig:
    st.caption("Compostos com menor score no Rank 1 — maior incerteza na identificação; revisão prioritária.")
    _bot = _base.dropna(subset=["pontuacao_rank1"]).nsmallest(_TOP, "pontuacao_rank1")
    st.dataframe(_tabela(_bot, _COLS_SRC, _COLS_DST), hide_index=True, use_container_width=True)

with tab_cands:
    st.caption("Compostos com o maior número de hipóteses moleculares.")
    _topc = _base.nlargest(_TOP, "n_candidatos")
    _cols_c_src = ["Sinal", "n_candidatos", "pontuacao_rank1", "melhor_candidato_curto"]
    _cols_c_dst = ["Composto", "N° candidatos", "Score Rank 1", "Candidato mais provável"]
    if _tem_criterio and "Criterio Desempate" in _base.columns:
        _cols_c_src.append("Criterio Desempate")
        _cols_c_dst.append("Critério de desempate")
    st.dataframe(_tabela(_topc, _cols_c_src, _cols_c_dst), hide_index=True, use_container_width=True)

with tab_empate:
    if _tem_empate:
        _emp_mask   = pd.to_numeric(rank1_unico["Empate"], errors="coerce").fillna(0) > 0
        _emp_sinais = rank1_unico[_emp_mask]["Sinal"].tolist()
        if _emp_sinais:
            st.caption(
                f"**{len(_emp_sinais)} composto(s)** com dois ou mais candidatos "
                "indistinguíveis automaticamente no Rank 1 — requerem decisão do especialista."
            )
            _emp_data = (
                _base[_base["Sinal"].isin(_emp_sinais)]
                [["Sinal", "n_candidatos", "pontuacao_rank1", "melhor_candidato_curto"]]
                .sort_values("n_candidatos", ascending=False)
            )
            _emp_data.columns = ["Composto", "N° candidatos", "Score Rank 1", "Candidato mais provável"]
            _emp_data["Score Rank 1"] = pd.to_numeric(_emp_data["Score Rank 1"], errors="coerce").round(1)
            st.dataframe(_emp_data.reset_index(drop=True), hide_index=True, use_container_width=True)

            _score_emp_cols = [c for c in [
                "Candidato", score_col, "Score Fragmentacao", "Score Lab", "Isotope Similarity"
            ] if c in rank1_df.columns]
            _rename_emp = {
                score_col: "Score",
                "Score Fragmentacao": "Fragmentação",
                "Isotope Similarity": "Isótopo",
            }
            _n_exibir  = min(10, len(_emp_sinais))
            _label_exp = (
                f"Candidatos em empate por composto ({_n_exibir} de {len(_emp_sinais)})"
                if len(_emp_sinais) > 10
                else f"Candidatos em empate por composto ({len(_emp_sinais)})"
            )
            with st.expander(_label_exp):
                for _sinal in _emp_sinais[:10]:
                    _g = rank1_df[rank1_df["Sinal"] == _sinal][_score_emp_cols].rename(columns=_rename_emp)
                    st.markdown(f"**{_sinal}**")
                    st.dataframe(_g, hide_index=True, use_container_width=True)
        else:
            st.success("Nenhum composto apresenta empate no Rank 1 neste experimento.")
    else:
        st.info("Informação de empate não disponível para esta análise (dados legados).")

st.divider()

# ===========================================================================
# BLOCO 3 — Qualidade da identificação
# ===========================================================================
st.subheader("Qualidade da identificação")

# --- Gráfico de discriminabilidade ---
if _tem_criterio and not criterio_counts.empty:
    st.caption(
        "Distribuição dos critérios que determinaram o Rank 1 para cada composto. "
        "Revela o poder de discriminação de cada nível do ranking hierárquico IST."
    )
    _col_crit, _col_crit_stats = st.columns([3, 1])

    with _col_crit:
        _bar_crit = (
            alt.Chart(criterio_counts)
            .mark_bar(opacity=0.88, cornerRadiusTopRight=2, cornerRadiusBottomRight=2)
            .encode(
                y=alt.Y("label:N", sort=None, title=None, axis=alt.Axis(labelLimit=200)),
                x=alt.X("n:Q", title="Compostos com Rank 1 determinado por este critério"),
                color=alt.Color("cor:N", scale=None, legend=None),
                tooltip=[
                    alt.Tooltip("label:N", title="Critério"),
                    alt.Tooltip("n:Q",     title="Compostos"),
                ],
            )
            .properties(height=max(200, len(criterio_counts) * 44))
        )
        st.altair_chart(_bar_crit, use_container_width=True)

    with _col_crit_stats:
        _pct_auto = n_resolvidos / n_compostos * 100 if n_compostos else 0.0
        st.metric(
            "Resolvidos automaticamente",
            f"{n_resolvidos} ({_pct_auto:.0f}%)",
            help="Compostos com Rank 1 determinado por critério automático",
        )
        st.metric(
            "Requerem decisão humana",
            n_nao_resolvidos,
            help="Compostos em empate — sem critério automático suficiente",
        )

    st.caption(
        "**Fragmentação MS/MS** é o critério de maior poder biológico (prioridade 1 no ranking IST). "
        "**Empate — decisão humana** indica compostos que requerem avaliação manual."
    )
    st.markdown("---")

# --- Distribuição de empates ---
if _tem_empate and n_empates > 0:
    st.markdown("**Distribuição de empates por número de candidatos**")
    _emp_mask2   = pd.to_numeric(rank1_unico["Empate"], errors="coerce").fillna(0) > 0
    _emp_sinais2 = rank1_unico[_emp_mask2]["Sinal"].tolist()
    _emp_size    = (
        rank1_df[rank1_df["Sinal"].isin(_emp_sinais2)]
        .groupby("Sinal")
        .size()
        .reset_index(name="n_empatados")
    )
    _dist_emp = _emp_size["n_empatados"].value_counts().reset_index()
    _dist_emp.columns = ["Candidatos empatados", "Compostos"]
    st.dataframe(_dist_emp.sort_values("Candidatos empatados"), hide_index=True, use_container_width=True)
    st.markdown("---")

# --- Histograma de scores ---
st.markdown("**Distribuição dos scores de identificação (Rank 1)**")
st.caption(
    "Score do candidato mais provável para cada composto. "
    "A linha vermelha pontilhada marca 80 — limiar de alta confiança."
)

if not rank1_unico.empty and rank1_unico[score_col].notna().any():
    _sp = rank1_unico[[score_col, "Sinal"]].rename(columns={score_col: "Pontuação"}).copy()
    _sp["Pontuação"] = pd.to_numeric(_sp["Pontuação"], errors="coerce")
    _sp = _sp.dropna(subset=["Pontuação"])
    if not _sp.empty:
        _hist = (
            alt.Chart(_sp)
            .mark_bar(color="#4472c4", opacity=0.85,
                      cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X("Pontuação:Q", bin=alt.Bin(step=10),
                        title="Score de identificação (Rank 1)",
                        axis=alt.Axis(values=list(range(0, 110, 10))),
                        scale=alt.Scale(domain=[0, 100])),
                y=alt.Y("count():Q", title="Compostos"),
                tooltip=[
                    alt.Tooltip("Pontuação:Q", bin=alt.Bin(step=10), title="Faixa de score"),
                    alt.Tooltip("count():Q", title="Compostos"),
                ],
            )
            .properties(height=220)
        )
        _linha_80 = (
            alt.Chart(pd.DataFrame({"v": [80.0]}))
            .mark_rule(color="#c0392b", strokeDash=[6, 3], opacity=0.65, size=1.5)
            .encode(x="v:Q")
        )
        st.altair_chart((_hist + _linha_80).properties(height=220), use_container_width=True)

st.divider()

# ===========================================================================
# BLOCO 4 — Perfil químico
# ===========================================================================
st.subheader("Perfil químico do experimento")
st.caption(
    "Classes químicas dos candidatos Rank 1 segundo PubChem / ChEBI. "
    "Revela a natureza dos compostos identificados neste experimento."
)

if not classes_classif.empty:
    _top_classes = classes_classif.head(12).sort_values("Frequência", ascending=True)
    _bar_cl = (
        alt.Chart(_top_classes)
        .mark_bar(color="#5a9e6f", opacity=0.82,
                  cornerRadiusTopRight=2, cornerRadiusBottomRight=2)
        .encode(
            y=alt.Y("Classe química:N", sort=None, title=None),
            x=alt.X("Frequência:Q", title="Compostos Rank 1 nesta classe"),
            tooltip=[
                alt.Tooltip("Classe química:N", title="Classe"),
                alt.Tooltip("Frequência:Q",     title="Compostos"),
            ],
        )
        .properties(height=max(160, len(_top_classes) * 32))
    )
    _col_cl, _col_cl_stats = st.columns([3, 1])
    with _col_cl:
        st.altair_chart(_bar_cl, use_container_width=True)
    with _col_cl_stats:
        st.metric("Classificados", f"{n_classif} / {n_compostos}",
                  help="Candidatos Rank 1 com classe química identificada")
        st.metric("Sem classificação", n_nc,
                  help="Candidatos sem classe documentada — frequente em compostos emergentes")
        if cobertura_ext:
            st.metric("Cobertura ChEBI",   f"{cobertura_ext.get('pct_chebi',   0):.0f}%",
                      help="% dos Rank 1 com identificador ChEBI em dim_molecula")
            st.metric("Cobertura PubChem", f"{cobertura_ext.get('pct_pubchem', 0):.0f}%",
                      help="% dos Rank 1 com identificador PubChem em dim_molecula")
    st.caption(
        "Compostos sem classificação não indicam erro — são frequentes em substâncias emergentes "
        "ou de síntese não catalogadas nas bases públicas."
    )
elif _tem_classes:
    st.info(
        "Nenhum Rank 1 possui classificação química documentada.  \n"
        "Comum em análises de compostos emergentes ou de síntese."
    )
else:
    st.info("Dados de classificação química não disponíveis para esta análise.")

st.divider()

# ===========================================================================
# Distribuição de ambiguidade molecular — gráfico exploratório
# ===========================================================================
st.subheader("Distribuição de ambiguidade molecular")
st.caption(
    "Cada ponto representa um composto. "
    "Eixo horizontal: número de candidatos; eixo vertical: score do Rank 1. "
    "Passe o cursor para detalhes."
)

if len(compound_data) >= 2:
    _sc = compound_data.dropna(subset=["pontuacao_rank1"]).copy()
    _sc["pontuacao_rank1"] = _sc["pontuacao_rank1"].round(1)
    _h_rule = (
        alt.Chart(pd.DataFrame({"y": [70.0]}))
        .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
        .encode(y="y:Q")
    )
    _v_rule = (
        alt.Chart(pd.DataFrame({"x": [float(compound_data["n_candidatos"].quantile(0.75))]}))
        .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
        .encode(x="x:Q")
    )
    _scatter = (
        alt.Chart(_sc)
        .mark_circle(opacity=0.78)
        .encode(
            x=alt.X("n_candidatos:Q", title="Candidatos moleculares", scale=alt.Scale(zero=True)),
            y=alt.Y("pontuacao_rank1:Q", title="Score Rank 1", scale=alt.Scale(domain=[0, 105])),
            size=alt.Size("n_candidatos:Q", scale=alt.Scale(range=[50, 260]), legend=None),
            color=alt.Color("pontuacao_rank1:Q",
                            scale=alt.Scale(scheme="blues", domain=[0, 100]),
                            legend=alt.Legend(title="Score Rank 1", orient="right")),
            tooltip=[
                alt.Tooltip("Sinal:N",             title="Composto"),
                alt.Tooltip("n_candidatos:Q",       title="Candidatos"),
                alt.Tooltip("pontuacao_rank1:Q",    title="Score Rank 1", format=".1f"),
                alt.Tooltip("melhor_candidato_curto:N", title="Rank 1"),
            ],
        )
        .properties(height=320)
    )
    st.altair_chart((_scatter + _h_rule + _v_rule).properties(height=320), use_container_width=True)
    st.caption(
        "**Superior esquerdo** — poucos candidatos, alta pontuação: identificação clara.  \n"
        "**Inferior direito** — muitos candidatos, baixa pontuação: alta ambiguidade, revisão prioritária."
    )
else:
    st.info("São necessários ao menos dois compostos para o gráfico de ambiguidade.")

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption("Omics ETL Pipeline · IST Ambiental / SENAI")
