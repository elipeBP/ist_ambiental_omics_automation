"""
Interface Streamlit — visualização do ranking de candidatos moleculares.

Execução:
    cd omics-etl-pipeline
    streamlit run src/ui/app.py
"""
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.ui.utils import (
    carregar_ranking,
    carregar_ranking_batch,
    listar_batches,
    db_existe,
)

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Omics ETL | IST Ambiental",
    page_icon="🧬",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Cabeçalho
# ---------------------------------------------------------------------------
st.title("🧬 Ranking de Candidatos Moleculares")
st.caption("Sistema de apoio à decisão para identificação de compostos | IST Ambiental / SENAI")
st.divider()

# ---------------------------------------------------------------------------
# Guarda de estado: banco inexistente
# ---------------------------------------------------------------------------
if not db_existe():
    st.warning(
        "Banco de dados não encontrado. "
        "Execute o pipeline primeiro:\n\n"
        "```bash\n"
        "cd omics-etl-pipeline\n"
        "python main.py\n"
        "```"
    )
    st.stop()

# ---------------------------------------------------------------------------
# Carrega lista de batches para o seletor (TTL curto — lista muda após uploads)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _listar_batches_ui() -> list:
    return listar_batches()


batches_todos   = _listar_batches_ui()
batches_sucesso = [b for b in batches_todos if b["status"] == "sucesso"]

# ---------------------------------------------------------------------------
# Sidebar — seletor de experimento (batch)
# ---------------------------------------------------------------------------
st.sidebar.header("Experimento")

# Recebe navegação de outras páginas (Histórico / Carregar Dados)
_ir_para = st.session_state.pop("ir_para_batch", None)

_MAIS_RECENTE = None
opcoes_ids    = [_MAIS_RECENTE] + [b["id"] for b in batches_sucesso]


def _label_batch(bid: "int | None") -> str:
    if bid is None:
        sufixo = f" (#{batches_sucesso[0]['id']})" if batches_sucesso else ""
        return f"Mais recente{sufixo}"
    b = next((x for x in batches_sucesso if x["id"] == bid), None)
    if not b:
        return f"Batch #{bid}"
    data = (b["iniciado_em"] or "")[:10]
    nome = b["nome_ident"]
    if len(nome) > 22:
        nome = nome[:19] + "..."
    return f"#{bid} — {data} | {nome}"


idx_default = 0
if _ir_para is not None and _ir_para in opcoes_ids:
    idx_default = opcoes_ids.index(_ir_para)

batch_sel_id = st.sidebar.selectbox(
    "Selecione o experimento:",
    options=opcoes_ids,
    index=idx_default,
    format_func=_label_batch,
)

st.sidebar.divider()

# ---------------------------------------------------------------------------
# Carregamento dos dados conforme seleção
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def _dados_completos() -> pd.DataFrame:
    return carregar_ranking()


@st.cache_data(ttl=300)
def _dados_batch(batch_id: int) -> pd.DataFrame:
    return carregar_ranking_batch(batch_id)


if batch_sel_id is None:
    df_completo = _dados_completos()
    batch_info  = None
else:
    df_completo = _dados_batch(batch_sel_id)
    batch_info  = next((b for b in batches_sucesso if b["id"] == batch_sel_id), None)

if df_completo.empty:
    st.info(
        "A view de ranking não retornou dados. "
        "Verifique se o pipeline foi executado com sucesso (`python main.py`)."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — filtro por sinal (depende dos dados carregados)
# ---------------------------------------------------------------------------
sinais = sorted(df_completo["Sinal"].dropna().unique().tolist())

st.sidebar.header("Filtros")
opcao_todos = "— Todos os sinais —"
sinal_escolhido = st.sidebar.selectbox(
    "Selecione um sinal analítico:",
    [opcao_todos] + sinais,
)

with st.sidebar.expander("ℹ️ Sobre o Score Ranking", expanded=False):
    st.markdown(
        """
        **Score Ranking** (0–100) — média ponderada dos scores de identificação:

        | Componente | Peso | Fonte |
        |---|---|---|
        | Fragmentação MS/MS | **40%** | Instrumento |
        | Score Lab | **30%** | Instrumento |
        | Similaridade Isotópica | **20%** | Instrumento |
        | Erro de Massa (ppm) | **10%** | Pipeline |

        *Pesos provisórios — calibráveis pelo IST.*

        ---
        **Score Qualidade Dados** (0–100%) — completude dos metadados
        externos (PubChem / ChEBI). Não entra no ranking.
        """
    )

# ---------------------------------------------------------------------------
# Detecção da coluna de score (backward compat)
# ---------------------------------------------------------------------------
score_col = "Score Ranking" if "Score Ranking" in df_completo.columns else "Score Total"

# ---------------------------------------------------------------------------
# Card de resumo do batch (somente quando experimento histórico está selecionado)
# ---------------------------------------------------------------------------
if batch_info:
    with st.container(border=True):
        st.markdown(f"#### Batch #{batch_info['id']} — análise histórica")
        c1, c2, c3 = st.columns(3)

        data_raw = batch_info.get("iniciado_em") or ""
        data_fmt = data_raw[:16].replace("T", " ") if data_raw else "—"
        c1.markdown(f"**Processado em**  \n{data_fmt}")

        c2.markdown(
            f"**Arquivos**  \n"
            f"{batch_info['nome_ident']}  \n"
            f"{batch_info['nome_abund']}"
        )

        sinais_n = batch_info.get("total_sinais")
        cand_n   = batch_info.get("total_candidatos")
        apis_n   = batch_info.get("total_moleculas_api")
        c3.markdown(
            f"**{sinais_n if sinais_n is not None else '—'}** sinais · "
            f"**{cand_n if cand_n is not None else '—'}** candidatos · "
            f"**{apis_n if apis_n is not None else '—'}** novas moléculas"
        )
    st.divider()

# ---------------------------------------------------------------------------
# Métricas resumidas (topo da página)
# ---------------------------------------------------------------------------
rank1 = df_completo[df_completo["Rank"] == 1]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total de sinais",     df_completo["Sinal"].nunique())
col2.metric("Total de candidatos", len(df_completo))
col3.metric(
    f"{score_col} médio (rank 1)",
    f"{rank1[score_col].mean():.1f}" if not rank1.empty else "—",
)
col4.metric(
    "Qualidade dados média",
    f"{df_completo['Score Qualidade Dados'].mean():.0f}%"
    if "Score Qualidade Dados" in df_completo.columns else "—",
)

st.divider()

# ---------------------------------------------------------------------------
# Visão geral — tabela principal
# ---------------------------------------------------------------------------
COLUNAS_RESUMO = ["Sinal", "m/z Medido", "Candidato", score_col, "Score Qualidade Dados", "Rank"]
COLUNAS_RESUMO = [c for c in COLUNAS_RESUMO if c in df_completo.columns]

st.subheader("Visão Geral")

df_exibir = (
    df_completo[COLUNAS_RESUMO].copy()
    if sinal_escolhido == opcao_todos
    else df_completo[df_completo["Sinal"] == sinal_escolhido][COLUNAS_RESUMO].copy()
)

st.dataframe(
    df_exibir,
    use_container_width=True,
    hide_index=True,
    column_config={
        score_col: st.column_config.ProgressColumn(
            score_col,
            help="Score de ranking (0–100) — média ponderada: Fragmentação 40% | Lab 30% | Isotopo 20% | Massa ppm 10%",
            min_value=0,
            max_value=100,
            format="%.1f",
        ),
        "Score Qualidade Dados": st.column_config.ProgressColumn(
            "Score Qualidade Dados",
            help="% dos metadados externos preenchidos (PubChem / ChEBI) — não entra no ranking",
            min_value=0,
            max_value=100,
            format="%.0f%%",
        ),
        "Rank": st.column_config.NumberColumn("Rank", help="1 = candidato mais plausível"),
    },
)

# ---------------------------------------------------------------------------
# Detalhamento — aparece somente quando um sinal é selecionado
# Filtra de df_completo (já carregado) — funciona para batch atual e histórico
# ---------------------------------------------------------------------------
if sinal_escolhido != opcao_todos:
    st.divider()
    st.subheader(f"Candidatos para o sinal `{sinal_escolhido}`")

    df_detalhe = df_completo[df_completo["Sinal"] == sinal_escolhido].copy()

    if df_detalhe.empty:
        st.warning("Nenhum candidato encontrado para este sinal.")
    else:
        melhor = df_detalhe[df_detalhe["Rank"] == 1]
        if not melhor.empty:
            nome_melhor  = melhor.iloc[0]["Candidato"]
            score_melhor = melhor.iloc[0].get(score_col, melhor.iloc[0].get("Score Total", 0))
            st.success(
                f"**Candidato mais plausível (Rank 1):** {nome_melhor} "
                f"— {score_col}: {score_melhor:.1f}/100"
            )

        # --- Dados laboratoriais (do equipamento) ---
        st.markdown("**Dados laboratoriais** *(scores gerados pelo instrumento)*")
        colunas_lab = [
            "Candidato", "Adducts", "Neutral Mass (Da)",
            "Score Lab", "Score Fragmentacao", "Mass Error (ppm)", "Isotope Similarity",
            "Rank",
        ]
        colunas_lab_presentes = [c for c in colunas_lab if c in df_detalhe.columns]
        st.dataframe(
            df_detalhe[colunas_lab_presentes],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score Lab":          st.column_config.ProgressColumn("Score Lab",          min_value=0, max_value=100, format="%.1f"),
                "Score Fragmentacao": st.column_config.ProgressColumn("Score Fragmentacao", min_value=0, max_value=100, format="%.1f"),
                "Mass Error (ppm)":   st.column_config.NumberColumn("Mass Error (ppm)",     format="%.4f"),
                "Isotope Similarity": st.column_config.ProgressColumn("Isotope Similarity", min_value=0, max_value=100, format="%.1f"),
                "Neutral Mass (Da)":  st.column_config.NumberColumn("Neutral Mass (Da)",    format="%.4f"),
                "Rank":               st.column_config.NumberColumn("Rank"),
            },
        )

        # --- Score Ranking (pipeline) ---
        st.markdown(
            "**Score Ranking** *(média ponderada — pesos provisórios, calibráveis pelo IST)*"
        )
        st.caption(
            "Fragmentação 40% · Score Lab 30% · Similaridade Isotópica 20% · "
            "Erro de Massa ppm 10% · Componentes nulos excluídos e pesos renormalizados"
        )

        colunas_score = ["Candidato", "Score Massa", score_col, "Score Qualidade Dados", "Rank"]
        colunas_score_presentes = [c for c in colunas_score if c in df_detalhe.columns]
        st.dataframe(
            df_detalhe[colunas_score_presentes],
            use_container_width=True,
            hide_index=True,
            column_config={
                score_col: st.column_config.ProgressColumn(
                    score_col,
                    help="Score de ranking (0–100)",
                    min_value=0, max_value=100, format="%.1f",
                ),
                "Score Qualidade Dados": st.column_config.ProgressColumn(
                    "Score Qualidade Dados",
                    help="Completude dos metadados externos — não entra no ranking",
                    min_value=0, max_value=100, format="%.0f%%",
                ),
                "Score Massa": st.column_config.NumberColumn(
                    "Score Massa (ppm)",
                    help="Componente do erro de massa em ppm (0–40) — contribui 10% no Score Ranking",
                    format="%.2f",
                ),
                "Rank": st.column_config.NumberColumn("Rank"),
            },
        )

        # Gráfico comparativo
        if len(df_detalhe) > 1:
            cols_grafico = [
                c for c in ["Score Fragmentacao", "Score Lab", "Isotope Similarity"]
                if c in df_detalhe.columns
            ]
            if cols_grafico:
                st.markdown("**Comparativo visual — scores do instrumento** *(componentes primários do ranking)*")
                st.bar_chart(
                    df_detalhe.set_index("Candidato")[cols_grafico],
                    use_container_width=True,
                )

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
view = "vw_ranking_historico" if batch_info else "vw_ranking_candidatos"
st.caption(f"Fonte: `{view}` | Banco: `banco_ist.db` | Pipeline: Omics ETL")
