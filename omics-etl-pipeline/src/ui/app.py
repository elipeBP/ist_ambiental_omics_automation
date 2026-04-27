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

from src.ui.utils import carregar_ranking, carregar_sinal, db_existe

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
# Carregamento dos dados
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def _dados_completos() -> pd.DataFrame:
    return carregar_ranking()


df_completo = _dados_completos()

if df_completo.empty:
    st.info(
        "A view de ranking não retornou dados. "
        "Verifique se o pipeline foi executado com sucesso (`python main.py`)."
    )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — filtro por sinal
# ---------------------------------------------------------------------------
sinais = sorted(df_completo["Sinal"].dropna().unique().tolist())

st.sidebar.header("Filtros")
opcao_todos = "— Todos os sinais —"
sinal_escolhido = st.sidebar.selectbox(
    "Selecione um sinal analítico:",
    [opcao_todos] + sinais,
)

# Informação sobre o modelo de scoring na sidebar
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
# Métricas resumidas (topo da página)
# ---------------------------------------------------------------------------
rank1 = df_completo[df_completo["Rank"] == 1]
score_col = "Score Ranking" if "Score Ranking" in df_completo.columns else "Score Total"

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
# ---------------------------------------------------------------------------
if sinal_escolhido != opcao_todos:
    st.divider()
    st.subheader(f"Candidatos para o sinal `{sinal_escolhido}`")

    df_detalhe = carregar_sinal(sinal_escolhido)

    if df_detalhe.empty:
        st.warning("Nenhum candidato encontrado para este sinal.")
    else:
        # Destaque do melhor candidato
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

        # Gráfico comparativo — scores do instrumento (mais relevantes para o ranking)
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
st.caption("Fonte: `vw_ranking_candidatos` | Banco: `banco_ist.db` | Pipeline: Omics ETL")
