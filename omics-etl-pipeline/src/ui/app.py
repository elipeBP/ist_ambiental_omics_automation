"""
Interface Streamlit — MVP de visualização do ranking de candidatos moleculares.

Execução:
    cd omics-etl-pipeline
    streamlit run src/ui/app.py
"""
import sys
from pathlib import Path

import streamlit as st
import pandas as pd

# Garante que o root do projeto está no path (necessário para importar src.ui.utils)
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
# Carregamento dos dados (com cache para não reabrir o banco a cada interação)
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

# ---------------------------------------------------------------------------
# Métricas resumidas (topo da página)
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Total de sinais", df_completo["Sinal"].nunique())
col2.metric("Total de candidatos", len(df_completo))
col3.metric(
    "Score médio (rank 1)",
    f"{df_completo[df_completo['Rank'] == 1]['Score Total'].mean():.1f}"
    if not df_completo[df_completo["Rank"] == 1].empty else "—",
)

st.divider()

# ---------------------------------------------------------------------------
# Visão geral — tabela principal
# ---------------------------------------------------------------------------
COLUNAS_RESUMO = ["Sinal", "m/z Medido", "Candidato", "Score Total", "Rank"]

st.subheader("Visão Geral")

if sinal_escolhido == opcao_todos:
    df_exibir = df_completo[COLUNAS_RESUMO].copy()
else:
    df_exibir = df_completo[df_completo["Sinal"] == sinal_escolhido][COLUNAS_RESUMO].copy()

st.dataframe(
    df_exibir,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Score Total": st.column_config.ProgressColumn(
            "Score Total",
            help="Score de plausibilidade (0–70)",
            min_value=0,
            max_value=70,
            format="%.2f",
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
            score_melhor = melhor.iloc[0]["Score Total"]
            st.success(f"**Candidato mais plausível (Rank 1):** {nome_melhor} — Score: {score_melhor:.2f}")

        # Tabela completa com todos os candidatos do sinal
        st.dataframe(
            df_detalhe,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Score Total": st.column_config.ProgressColumn(
                    "Score Total",
                    min_value=0,
                    max_value=70,
                    format="%.2f",
                ),
                "Score Massa": st.column_config.NumberColumn("Score Massa", format="%.2f"),
                "Score Metadata": st.column_config.NumberColumn("Score Metadata", format="%.2f"),
                "Rank": st.column_config.NumberColumn("Rank"),
            },
        )

        # Gráfico de scores por candidato (útil quando há múltiplos candidatos)
        if len(df_detalhe) > 1:
            st.bar_chart(
                df_detalhe.set_index("Candidato")[["Score Massa", "Score Metadata"]],
                use_container_width=True,
            )

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption("Fonte: `vw_ranking_candidatos` | Banco: `banco_ist.db` | Pipeline: Omics ETL")
