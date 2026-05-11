"""
Página: Insights Analíticos
Exploração visual dos resultados do experimento — apoio à interpretação analítica.
"""
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.ui.utils import carregar_ranking, carregar_ranking_batch, db_existe, listar_batches

st.set_page_config(
    page_title="Insights Analíticos | Omics ETL",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Insights Analíticos")
st.caption(
    "Exploração visual dos resultados — indicadores de apoio à interpretação analítica "
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
# Seletor de análise (sidebar) — mesmo padrão das outras páginas
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

# ---------------------------------------------------------------------------
# Detecção da coluna de score (backward compat)
# ---------------------------------------------------------------------------
score_col = "Score Ranking" if "Score Ranking" in df.columns else "Score Total"

# ---------------------------------------------------------------------------
# Preparação dos dados analíticos
# ---------------------------------------------------------------------------

# Rank 1 deduplicado por composto (um registro por sinal — resolve empates)
rank1_df = (
    df[df["Rank"] == 1]
    .sort_values(score_col, ascending=False)
    .drop_duplicates(subset=["Sinal"])
    .copy()
)

# Contagem de candidatos por composto
compound_counts = df.groupby("Sinal").size().reset_index(name="n_candidatos")

# Dados por composto: candidatos + score Rank 1 + melhor candidato
rank1_slim = rank1_df[["Sinal", score_col, "Candidato"]].copy().rename(
    columns={score_col: "pontuacao_rank1", "Candidato": "melhor_candidato"}
)
compound_data = compound_counts.merge(rank1_slim, on="Sinal", how="left")
compound_data["pontuacao_rank1"] = pd.to_numeric(
    compound_data["pontuacao_rank1"], errors="coerce"
)
compound_data["melhor_candidato_curto"] = compound_data["melhor_candidato"].apply(
    lambda s: (s[:50] + "…") if isinstance(s, str) and len(s) > 50 else s
)

# Métricas gerais
n_compostos      = len(compound_data)
n_candidatos_tot = len(df)
mean_pontuacao   = float(rank1_df[score_col].mean()) if not rank1_df.empty else 0.0
mean_qualidade   = float(df["Score Qualidade Dados"].mean()) if "Score Qualidade Dados" in df.columns else 0.0
mean_cand_comp   = n_candidatos_tot / n_compostos if n_compostos else 0.0
n_alta_conf      = int((rank1_df[score_col] > 80).sum()) if not rank1_df.empty else 0

# Classes químicas dos Rank 1 (limpas)
_tem_classes = "Classe Quimica" in rank1_df.columns
if _tem_classes:
    classes_raw    = rank1_df["Classe Quimica"].fillna("Não classificada")
    classes_raw    = classes_raw.replace("Nao classificada", "Não classificada")
    classes_cnt    = classes_raw.value_counts().reset_index()
    classes_cnt.columns = ["Classe química", "Frequência"]
    classes_classif = classes_cnt[classes_cnt["Classe química"] != "Não classificada"]
    n_nc           = int(classes_cnt.loc[classes_cnt["Classe química"] == "Não classificada", "Frequência"].sum())
    n_classif      = int(classes_classif["Frequência"].sum())
else:
    classes_cnt     = pd.DataFrame()
    classes_classif = pd.DataFrame()
    n_nc            = 0
    n_classif       = 0

pct_classif = n_classif / n_compostos * 100 if n_compostos else 0.0

# ---------------------------------------------------------------------------
# Identificação da análise exibida
# ---------------------------------------------------------------------------
batch_info = next((b for b in batches_sucesso if b["id"] == batch_sel), None) if batch_sel else None
if batch_info:
    d_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
    st.info(
        f"**Análise #{batch_info['id']}** — {d_raw} | {batch_info['nome_ident']}"
    )

# ---------------------------------------------------------------------------
# Métricas principais
# ---------------------------------------------------------------------------
m1, m2, m3, m4, m5, m6 = st.columns(6)
m1.metric(
    "Compostos detectados",
    n_compostos,
    help="Sinais analíticos únicos identificados pelo instrumento neste experimento",
)
m2.metric(
    "Total de candidatos",
    n_candidatos_tot,
    help="Soma de todos os candidatos moleculares para todos os compostos detectados",
)
m3.metric(
    "Confiança média (Rank 1)",
    f"{mean_pontuacao:.1f}",
    help="Pontuação média de identificação dos candidatos mais prováveis de cada composto (0–100)",
)
m4.metric(
    "Candidatos por composto",
    f"{mean_cand_comp:.1f}",
    help="Média de candidatos moleculares por composto — valores altos indicam maior ambiguidade",
)
m5.metric(
    "Alta confiança (> 80)",
    f"{n_alta_conf} / {n_compostos}",
    help="Compostos cujo candidato mais provável (Rank 1) possui pontuação acima de 80",
)
m6.metric(
    "Dados externos disponíveis",
    f"{mean_qualidade:.0f}%",
    help="Percentual médio de informações encontradas em bases públicas (PubChem, ChEBI)",
)

st.divider()

# ---------------------------------------------------------------------------
# Leitura rápida do experimento
# ---------------------------------------------------------------------------
st.subheader("Leitura rápida do experimento")

_insights: list[tuple[str, str]] = []

# 1 — Confiança geral
if mean_pontuacao >= 75:
    _insights.append(("success",
        f"**Alta confiança geral:** pontuação média dos candidatos mais prováveis é "
        f"**{mean_pontuacao:.1f}/100** — identificações com boa correspondência espectral."
    ))
elif mean_pontuacao >= 50:
    _insights.append(("info",
        f"**Confiança moderada:** pontuação média dos candidatos mais prováveis é "
        f"**{mean_pontuacao:.1f}/100** — recomenda-se avaliação individual dos compostos com scores mais baixos."
    ))
else:
    _insights.append(("warning",
        f"**Baixa confiança geral:** pontuação média de **{mean_pontuacao:.1f}/100** — "
        "o experimento apresenta alta ambiguidade e requer revisão detalhada pelo especialista."
    ))

# 2 — Ambiguidade
if mean_cand_comp >= 15:
    _insights.append(("warning",
        f"**Alta ambiguidade molecular:** média de **{mean_cand_comp:.1f} candidatos por composto** — "
        "muitos sinais possuem diversas identidades compatíveis, dificultando a distinção automática."
    ))
elif mean_cand_comp <= 5:
    _insights.append(("success",
        f"**Baixa ambiguidade:** média de **{mean_cand_comp:.1f} candidatos por composto** — "
        "a maioria dos sinais possui poucas identidades alternativas."
    ))
else:
    _insights.append(("info",
        f"**Ambiguidade moderada:** média de **{mean_cand_comp:.1f} candidatos por composto**."
    ))

# 3 — Cobertura de alta confiança
pct_alta = n_alta_conf / n_compostos * 100 if n_compostos else 0.0
if pct_alta >= 50:
    _insights.append(("success",
        f"**{n_alta_conf} de {n_compostos} compostos ({pct_alta:.0f}%)** possuem Rank 1 "
        "com pontuação acima de 80 — boa cobertura de identificações confiáveis."
    ))
elif n_alta_conf > 0:
    _insights.append(("info",
        f"**{n_alta_conf} de {n_compostos} compostos ({pct_alta:.0f}%)** possuem Rank 1 "
        "com pontuação acima de 80."
    ))
else:
    _insights.append(("warning",
        f"**Nenhum composto** possui Rank 1 com pontuação acima de 80 — "
        "todas as identificações requerem validação manual."
    ))

# 4 — Classificação química
if n_compostos > 0:
    if pct_classif >= 60:
        _insights.append(("success",
            f"**{pct_classif:.0f}% dos candidatos mais prováveis** foram classificados "
            "quimicamente em bases públicas (PubChem / ChEBI)."
        ))
    elif pct_classif >= 25:
        _insights.append(("info",
            f"**{pct_classif:.0f}% dos candidatos mais prováveis** possuem classificação "
            "química em bases públicas."
        ))
    else:
        _insights.append(("info",
            "**A maioria dos candidatos mais prováveis não possui classificação química documentada** "
            "— frequente em compostos emergentes, de síntese ou pouco estudados. "
            "Não indica problema na identificação."
        ))

with st.container(border=True):
    for tipo, texto in _insights:
        if tipo == "success":
            st.success(texto)
        elif tipo == "warning":
            st.warning(texto)
        else:
            st.info(texto)

st.divider()

# ---------------------------------------------------------------------------
# Seção 1 — Distribuição das pontuações de identificação
# ---------------------------------------------------------------------------
st.subheader("Distribuição das pontuações de identificação")
st.caption(
    "Pontuação de identificação do candidato mais provável (Rank 1) para cada composto detectado. "
    "Mostra quão confiante o instrumento está nas identificações deste experimento."
)

if not rank1_df.empty and rank1_df[score_col].notna().any():
    scores_plot = rank1_df[[score_col, "Sinal"]].copy()
    scores_plot = scores_plot.rename(columns={score_col: "Pontuação"})
    scores_plot["Pontuação"] = pd.to_numeric(scores_plot["Pontuação"], errors="coerce")
    scores_plot = scores_plot.dropna(subset=["Pontuação"])

    hist = (
        alt.Chart(scores_plot)
        .mark_bar(color="#4472c4", opacity=0.85, cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
        .encode(
            x=alt.X(
                "Pontuação:Q",
                bin=alt.Bin(step=10),
                title="Pontuação de identificação (Rank 1)",
                axis=alt.Axis(values=list(range(0, 110, 10))),
                scale=alt.Scale(domain=[0, 100]),
            ),
            y=alt.Y("count():Q", title="Número de compostos"),
            tooltip=[
                alt.Tooltip("Pontuação:Q", bin=alt.Bin(step=10), title="Faixa de pontuação"),
                alt.Tooltip("count():Q", title="Compostos nesta faixa"),
            ],
        )
        .properties(height=280)
    )

    linha_80 = (
        alt.Chart(pd.DataFrame({"v": [80.0]}))
        .mark_rule(color="#c0392b", strokeDash=[6, 3], opacity=0.65, size=1.5)
        .encode(x="v:Q")
    )

    st.altair_chart((hist + linha_80).properties(height=280), use_container_width=True)
    st.caption(
        "A linha vermelha pontilhada marca a pontuação 80 — limiar de alta confiança. "
        "Distribuições deslocadas para a esquerda (< 50) indicam experimentos com alta ambiguidade geral; "
        "concentrações acima de 70 indicam boa qualidade de identificação."
    )
else:
    st.info("Dados insuficientes para o histograma.")

st.divider()

# ---------------------------------------------------------------------------
# Seção 2 — Ambiguidade molecular
# ---------------------------------------------------------------------------
st.subheader("Ambiguidade molecular")

col_desc, _ = st.columns([3, 1])
with col_desc:
    st.caption(
        "Cada ponto representa um composto detectado. "
        "O eixo horizontal mostra quantos candidatos foram sugeridos; "
        "o eixo vertical mostra a pontuação do candidato mais provável (Rank 1). "
        "Passe o cursor sobre um ponto para ver os detalhes."
    )

if len(compound_data) >= 2:
    scatter_df = compound_data.dropna(subset=["pontuacao_rank1"]).copy()
    scatter_df["pontuacao_rank1"] = scatter_df["pontuacao_rank1"].round(1)

    # Linhas de referência dos quadrantes
    h_rule = (
        alt.Chart(pd.DataFrame({"y": [70.0]}))
        .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
        .encode(y="y:Q")
    )
    v_rule = (
        alt.Chart(pd.DataFrame({"x": [float(compound_data["n_candidatos"].quantile(0.75))]}))
        .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.35, size=1)
        .encode(x="x:Q")
    )

    scatter = (
        alt.Chart(scatter_df)
        .mark_circle(opacity=0.80)
        .encode(
            x=alt.X(
                "n_candidatos:Q",
                title="Número de candidatos moleculares",
                scale=alt.Scale(zero=True),
            ),
            y=alt.Y(
                "pontuacao_rank1:Q",
                title="Pontuação de identificação (Rank 1)",
                scale=alt.Scale(domain=[0, 105]),
            ),
            size=alt.Size(
                "n_candidatos:Q",
                scale=alt.Scale(range=[60, 300]),
                legend=None,
            ),
            color=alt.Color(
                "pontuacao_rank1:Q",
                scale=alt.Scale(scheme="blues", domain=[0, 100]),
                legend=alt.Legend(title="Pontuação Rank 1", orient="right"),
            ),
            tooltip=[
                alt.Tooltip("Sinal:N", title="Composto"),
                alt.Tooltip("n_candidatos:Q", title="Candidatos"),
                alt.Tooltip("pontuacao_rank1:Q", title="Pontuação Rank 1", format=".1f"),
                alt.Tooltip("melhor_candidato_curto:N", title="Melhor candidato"),
            ],
        )
        .properties(height=360)
    )

    st.altair_chart((scatter + h_rule + v_rule).properties(height=360), use_container_width=True)

    col_q1, col_q2 = st.columns(2)
    with col_q1:
        with st.container(border=True):
            st.markdown("**Superior esquerdo — identificação clara**")
            st.caption("Poucos candidatos e alta pontuação. O instrumento encontrou poucos compostos compatíveis e o melhor deles tem boa correspondência espectral.")
    with col_q2:
        with st.container(border=True):
            st.markdown("**Inferior direito — alta ambiguidade**")
            st.caption("Muitos candidatos e baixa pontuação. Diversas moléculas são compatíveis com o sinal e nenhuma se destaca — requer revisão prioritária pelo especialista.")

    st.divider()

    # Bar: compostos com mais candidatos
    top_n      = min(15, len(compound_data))
    top_comp   = compound_data.nlargest(top_n, "n_candidatos").copy()
    top_comp   = top_comp.sort_values("n_candidatos", ascending=True)

    st.markdown(f"**Compostos com maior número de candidatos** (top {top_n})")
    st.caption("Compostos com muitos candidatos e baixa pontuação representam os casos de maior ambiguidade e são prioritários na revisão manual.")

    bar_cands = (
        alt.Chart(top_comp)
        .mark_bar(color="#4472c4", opacity=0.82, cornerRadiusTopRight=2, cornerRadiusBottomRight=2)
        .encode(
            y=alt.Y("Sinal:N", sort=None, title="Composto detectado"),
            x=alt.X("n_candidatos:Q", title="Número de candidatos moleculares"),
            color=alt.Color(
                "pontuacao_rank1:Q",
                scale=alt.Scale(scheme="blues", domain=[0, 100]),
                legend=alt.Legend(title="Pontuação Rank 1"),
            ),
            tooltip=[
                alt.Tooltip("Sinal:N", title="Composto"),
                alt.Tooltip("n_candidatos:Q", title="Candidatos"),
                alt.Tooltip("pontuacao_rank1:Q", title="Pontuação Rank 1", format=".1f"),
                alt.Tooltip("melhor_candidato_curto:N", title="Melhor candidato"),
            ],
        )
        .properties(height=max(200, top_n * 32))
    )

    st.altair_chart(bar_cands, use_container_width=True)

else:
    st.info("São necessários ao menos dois compostos para exibir o gráfico de ambiguidade.")

st.divider()

# ---------------------------------------------------------------------------
# Seção 3 — Perfil químico do experimento
# ---------------------------------------------------------------------------
st.subheader("Perfil químico do experimento")
st.caption(
    "Classes químicas dos candidatos mais prováveis (Rank 1) segundo ChEBI. "
    "Revela o perfil geral dos compostos identificados nesta análise."
)

if not classes_classif.empty:
    top_classes = classes_classif.head(12).sort_values("Frequência", ascending=True)

    bar_classes = (
        alt.Chart(top_classes)
        .mark_bar(color="#5a9e6f", opacity=0.82, cornerRadiusTopRight=2, cornerRadiusBottomRight=2)
        .encode(
            y=alt.Y("Classe química:N", sort=None, title=None),
            x=alt.X("Frequência:Q", title="Compostos classificados (Rank 1)"),
            tooltip=[
                alt.Tooltip("Classe química:N", title="Classe"),
                alt.Tooltip("Frequência:Q", title="Compostos"),
            ],
        )
        .properties(height=max(160, len(top_classes) * 32))
    )

    col_chart, col_stats = st.columns([3, 1])
    with col_chart:
        st.altair_chart(bar_classes, use_container_width=True)

    with col_stats:
        st.metric(
            "Classificados",
            f"{n_classif} / {n_compostos}",
            help="Candidatos Rank 1 com classe química identificada em PubChem ou ChEBI",
        )
        st.metric(
            "Sem classificação",
            n_nc,
            help="Candidatos sem classe química documentada — comum em compostos emergentes ou pouco estudados",
        )
        if len(classes_classif) > 0:
            classe_dom = classes_classif.iloc[0]["Classe química"]
            freq_dom   = classes_classif.iloc[0]["Frequência"]
            st.metric(
                "Classe predominante",
                f"{freq_dom} comp.",
                help=f"Classe mais frequente: {classe_dom}",
            )

    st.caption(
        "Classes predominantes revelam o perfil químico do experimento. "
        "Compostos sem classificação não indicam erro — são frequentes em substâncias emergentes "
        "ou de síntese não catalogadas nas bases públicas."
    )

elif _tem_classes:
    st.info(
        "Nenhum candidato mais provável possui classificação química documentada em bases públicas.  \n"
        "Isso é comum em análises de compostos emergentes ou de síntese."
    )
else:
    st.info("Dados de classificação química não disponíveis para esta análise.")

st.divider()

# ---------------------------------------------------------------------------
# Seção 4 — Scores instrumentais (Rank 1)
# ---------------------------------------------------------------------------
_SCORE_COLS_LAB = ["Score Lab", "Score Fragmentacao", "Isotope Similarity"]
_SCORE_LABELS   = {
    "Score Lab":          "Score do instrumento",
    "Score Fragmentacao": "Correspondência MS/MS",
    "Isotope Similarity": "Padrão isotópico",
}
_cols_ok = [c for c in _SCORE_COLS_LAB if c in rank1_df.columns]

if len(_cols_ok) >= 2 and not rank1_df.empty:
    st.subheader("Scores instrumentais — distribuição (Rank 1)")
    st.caption(
        "Distribuição dos sub-scores do instrumento para os candidatos mais prováveis. "
        "Compara como cada critério se comporta ao longo do experimento."
    )

    scores_long = (
        rank1_df[_cols_ok + ["Sinal"]]
        .melt(id_vars="Sinal", var_name="Score", value_name="Valor")
    )
    scores_long["Score"] = scores_long["Score"].map(_SCORE_LABELS).fillna(scores_long["Score"])
    scores_long["Valor"] = pd.to_numeric(scores_long["Valor"], errors="coerce")
    scores_long = scores_long.dropna(subset=["Valor"])

    # Médias por score (para anotação)
    medias = scores_long.groupby("Score")["Valor"].mean().reset_index().rename(columns={"Valor": "Media"})

    box_chart = (
        alt.Chart(scores_long)
        .mark_boxplot(extent="min-max", size=50, median=alt.MarkConfig(color="white", size=50))
        .encode(
            x=alt.X("Score:N", title=None, axis=alt.Axis(labelAngle=0)),
            y=alt.Y(
                "Valor:Q",
                title="Valor (0–100)",
                scale=alt.Scale(domain=[0, 105]),
            ),
            color=alt.Color(
                "Score:N",
                scale=alt.Scale(
                    domain=list(_SCORE_LABELS.values()),
                    range=["#4472c4", "#c0392b", "#5a9e6f"],
                ),
                legend=None,
            ),
        )
        .properties(height=300)
    )

    media_points = (
        alt.Chart(medias)
        .mark_text(dy=-12, fontSize=11, fontWeight="bold")
        .encode(
            x=alt.X("Score:N"),
            y=alt.Y("Media:Q"),
            text=alt.Text("Media:Q", format=".1f"),
            color=alt.Color("Score:N", scale=alt.Scale(
                domain=list(_SCORE_LABELS.values()),
                range=["#4472c4", "#c0392b", "#5a9e6f"],
            ), legend=None),
        )
    )

    st.altair_chart((box_chart + media_points).properties(height=300), use_container_width=True)
    st.caption(
        "Cada caixa mostra a mediana (linha branca), o intervalo interquartil (caixa) "
        "e os valores mínimo e máximo (hastes) para o conjunto de compostos. "
        "O número acima de cada caixa é a média do score. "
        "Caixas estreitas indicam scores consistentes entre os compostos; "
        "caixas largas revelam maior variabilidade."
    )

    st.divider()

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.caption("Omics ETL Pipeline · IST Ambiental / SENAI")
