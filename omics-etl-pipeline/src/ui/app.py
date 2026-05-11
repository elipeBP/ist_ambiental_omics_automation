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
st.title("🧬 Identificação de Compostos — Resultados")
st.caption("Candidatos moleculares sugeridos pelo instrumento, organizados por plausibilidade de identificação | IST Ambiental / SENAI")
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
# Carrega lista de batches para o seletor (TTL curto — lista muda após uploads)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=30)
def _listar_batches_ui() -> list:
    return listar_batches()


batches_todos   = _listar_batches_ui()
batches_sucesso = [b for b in batches_todos if b["status"] == "sucesso"]

# ---------------------------------------------------------------------------
# Sidebar — seletor de análise
# ---------------------------------------------------------------------------
st.sidebar.header("Análise")

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
        return f"Análise #{bid}"
    data = (b["iniciado_em"] or "")[:10]
    nome = b["nome_ident"]
    if len(nome) > 22:
        nome = nome[:19] + "..."
    return f"#{bid} — {data} | {nome}"


idx_default = 0
if _ir_para is not None and _ir_para in opcoes_ids:
    idx_default = opcoes_ids.index(_ir_para)

batch_sel_id = st.sidebar.selectbox(
    "Selecionar análise:",
    options=opcoes_ids,
    index=idx_default,
    format_func=_label_batch,
    help="Selecione um experimento para visualizar os resultados. 'Mais recente' exibe o último processado com sucesso.",
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
    if batch_sel_id is not None:
        st.warning(
            f"Nenhum resultado encontrado para a **Análise #{batch_sel_id}**.  \n"
            "A análise pode não ter sido concluída com sucesso."
        )
    else:
        st.info(
            "Nenhum experimento processado ainda.  \n"
            "Use a página **📤 Nova Análise** para processar um experimento."
        )
    st.stop()

# ---------------------------------------------------------------------------
# Sidebar — filtro por composto (depende dos dados carregados)
# ---------------------------------------------------------------------------
try:
    sinais = sorted(df_completo["Sinal"].dropna().unique().tolist())
except KeyError:
    sinais = []

st.sidebar.header("Filtros")
opcao_todos = "— Todos os compostos —"
sinal_escolhido = st.sidebar.selectbox(
    "Filtrar por composto detectado:",
    [opcao_todos] + sinais,
    help="Selecione um composto para ver todos os seus candidatos moleculares em detalhe.",
)

with st.sidebar.expander("ℹ️ Como interpretar a pontuação", expanded=False):
    st.markdown(
        """
        **Pontuação de identificação** (0–100)

        Calculada a partir dos dados do instrumento LC-MS/MS.
        Candidatos com pontuação mais alta correspondem melhor
        ao sinal medido — são os mais *prováveis*, não os confirmados.

        O instrumento avalia automaticamente:
        - Coincidência com o padrão de fragmentação MS/MS
        - Semelhança com o padrão isotópico esperado
        - Precisão do erro de massa

        ---
        **Dados externos disponíveis** (0–100%)

        Indica quantas informações sobre o candidato foram
        encontradas em bases públicas (PubChem, ChEBI).
        **Não afeta o ranking** — é um indicador de quão bem
        documentada é a molécula na literatura científica.

        ---
        ⚠️ *Os resultados devem ser validados por especialista
        antes de reportar uma identificação definitiva.*
        """
    )

st.sidebar.divider()
st.sidebar.caption("Omics ETL · IST Ambiental / SENAI")

# ---------------------------------------------------------------------------
# Detecção da coluna de score (backward compat)
# ---------------------------------------------------------------------------
score_col = "Score Ranking" if "Score Ranking" in df_completo.columns else "Score Total"

# ---------------------------------------------------------------------------
# Card de resumo da análise histórica (somente quando selecionado)
# ---------------------------------------------------------------------------
if batch_info:
    st.info(
        f"**Visualizando Análise Histórica #{batch_info['id']}** — "
        "os resultados exibidos correspondem a este experimento específico. "
        "Para retornar à análise mais recente, selecione **Mais recente** na barra lateral."
    )
    with st.container(border=True):
        st.markdown(f"#### Análise #{batch_info['id']}")
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
            f"**{sinais_n if sinais_n is not None else '—'}** compostos detectados · "
            f"**{cand_n if cand_n is not None else '—'}** candidatos · "
            f"**{apis_n if apis_n is not None else '—'}** moléculas buscadas online"
        )
    st.divider()

# ---------------------------------------------------------------------------
# Métricas resumidas
# ---------------------------------------------------------------------------
rank1 = df_completo[df_completo["Rank"] == 1]

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Compostos detectados",
    df_completo["Sinal"].nunique(),
    help="Número de sinais analíticos únicos identificados pelo instrumento neste experimento",
)
col2.metric(
    "Identidades sugeridas",
    len(df_completo),
    help="Total de candidatos moleculares listados para todos os compostos detectados",
)
col3.metric(
    "Confiança média (Rank 1)",
    f"{rank1[score_col].mean():.1f}" if not rank1.empty else "—",
    help="Pontuação média de identificação dos candidatos mais prováveis (Rank 1) de cada composto",
)
col4.metric(
    "Dados externos disponíveis",
    f"{df_completo['Score Qualidade Dados'].mean():.0f}%"
    if "Score Qualidade Dados" in df_completo.columns else "—",
    help="Percentual médio de informações encontradas em bases públicas (PubChem, ChEBI) para os candidatos",
)

st.divider()

# ---------------------------------------------------------------------------
# Fluxo conceitual — contexto para novos usuários
# ---------------------------------------------------------------------------
with st.expander("ℹ️ Como interpretar estes resultados", expanded=False):
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        with st.container(border=True):
            st.markdown("**🔬 Instrumento LC-MS/MS**")
            st.caption(
                "Detecta sinais na amostra e, para cada um, sugere compostos candidatos "
                "com base em bibliotecas espectrais e critérios de correspondência de massa."
            )
    with fc2:
        with st.container(border=True):
            st.markdown("**🖥️ Este sistema**")
            st.caption(
                "Organiza os candidatos por pontuação de identificação e enriquece "
                "com informações de bases de dados científicas (PubChem, ChEBI)."
            )
    with fc3:
        with st.container(border=True):
            st.markdown("**🧪 Especialista analítico**")
            st.caption(
                "Valida o Rank 1 considerando o contexto químico da amostra. "
                "O sistema apoia a decisão — não a substitui."
            )
    st.caption(
        "Cada **composto detectado** pode ter dezenas de **candidatos moleculares**. "
        "O **Rank 1** é o mais compatível com o sinal medido — "
        "a identificação definitiva requer avaliação do especialista."
    )

# ---------------------------------------------------------------------------
# Visão geral — tabela principal
# ---------------------------------------------------------------------------
COLUNAS_RESUMO = ["Sinal", "m/z Medido", "Candidato", score_col, "Score Qualidade Dados", "Rank"]
COLUNAS_RESUMO = [c for c in COLUNAS_RESUMO if c in df_completo.columns]

st.subheader("Todos os candidatos do experimento")

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
        "Sinal": st.column_config.TextColumn(
            "Composto detectado",
            help="Código do sinal analítico atribuído pelo instrumento. Formato: tempo_de_retenção_m/z. Use o filtro lateral para explorar um composto específico.",
        ),
        "m/z Medido": st.column_config.NumberColumn(
            "m/z medido",
            help="Razão massa/carga registrada pelo instrumento para este sinal. Valor instrumental — não é a massa molecular diretamente.",
            format="%.4f",
        ),
        "Candidato": st.column_config.TextColumn(
            "Candidato molecular",
            help="Nome do composto sugerido como possível identidade deste sinal. Pode haver múltiplos candidatos por composto detectado.",
        ),
        score_col: st.column_config.ProgressColumn(
            "Pontuação de identificação",
            help="Score calculado pelo instrumento (0–100). Integra fragmentação MS/MS, padrão isotópico e erro de massa. Quanto maior, mais compatível com o sinal medido.",
            min_value=0,
            max_value=100,
            format="%.1f",
        ),
        "Score Qualidade Dados": st.column_config.ProgressColumn(
            "Dados externos disponíveis",
            help="% de informações encontradas em bases científicas públicas (PubChem, ChEBI). Indica quão bem documentado é o candidato — não afeta o ranking.",
            min_value=0,
            max_value=100,
            format="%.0f%%",
        ),
        "Rank": st.column_config.NumberColumn(
            "Rank",
            help="Posição entre os candidatos deste composto. Rank 1 = candidato mais provável segundo o instrumento.",
        ),
    },
)

# ---------------------------------------------------------------------------
# Detalhamento — aparece somente quando um composto é selecionado
# ---------------------------------------------------------------------------
if sinal_escolhido != opcao_todos:
    st.divider()
    st.subheader(f"Composto: `{sinal_escolhido}`")
    st.caption(
        "Candidatos moleculares sugeridos pelo instrumento, do mais ao menos provável. "
        "Rank 1 = maior pontuação de identificação para este composto."
    )

    df_detalhe = df_completo[df_completo["Sinal"] == sinal_escolhido].copy()

    if df_detalhe.empty:
        st.warning("Nenhum candidato encontrado para este composto.")
    else:
        melhor = df_detalhe[df_detalhe["Rank"] == 1]
        if not melhor.empty:
            nome_melhor  = melhor.iloc[0]["Candidato"]
            score_melhor = melhor.iloc[0].get(score_col, melhor.iloc[0].get("Score Total", 0))
            st.success(
                f"**Candidato mais provável (Rank 1):** {nome_melhor}  \n"
                f"Pontuação de identificação: **{score_melhor:.1f} / 100**  \n"
                "Este é o composto considerado mais compatível com o sinal pelo instrumento. "
                "Recomenda-se confirmação por especialista antes de reportar."
            )

        # --- Detalhes da identificação instrumental ---
        st.markdown("**Detalhes da identificação instrumental**")
        st.caption(
            "Valores gerados pelo instrumento para cada candidato. "
            "Úteis para investigar por que um candidato foi melhor ou pior posicionado."
        )
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
                "Candidato": st.column_config.TextColumn("Candidato molecular"),
                "Adducts": st.column_config.TextColumn(
                    "Forma iônica detectada",
                    help="Como a molécula foi ionizada durante a análise. Ex.: 'M-H' = perda de um próton; 'M+Na' = adição de sódio. Afeta o cálculo da massa molecular.",
                ),
                "Neutral Mass (Da)": st.column_config.NumberColumn(
                    "Massa molecular calc. (Da)",
                    help="Massa molecular calculada a partir do sinal medido, descontando o efeito da ionização. Em Daltons (Da).",
                    format="%.4f",
                ),
                "Score Lab": st.column_config.ProgressColumn(
                    "Score do instrumento",
                    help="Pontuação geral calculada pelo software do equipamento LC-MS/MS, integrando todos os critérios de identificação.",
                    min_value=0, max_value=100, format="%.1f",
                ),
                "Score Fragmentacao": st.column_config.ProgressColumn(
                    "Correspondência MS/MS",
                    help="Grau de coincidência entre os fragmentos detectados e o padrão esperado para este composto. Componente do score do instrumento.",
                    min_value=0, max_value=100, format="%.1f",
                ),
                "Mass Error (ppm)": st.column_config.NumberColumn(
                    "Erro de massa (ppm)",
                    help="Diferença entre a massa medida e a massa teórica, em partes por milhão (ppm). Valores próximos de zero indicam melhor correspondência de massa.",
                    format="%.4f",
                ),
                "Isotope Similarity": st.column_config.ProgressColumn(
                    "Padrão isotópico",
                    help="Semelhança entre o padrão de isótopos medido e o esperado para a fórmula molecular do candidato. Componente do score do instrumento.",
                    min_value=0, max_value=100, format="%.1f",
                ),
                "Rank": st.column_config.NumberColumn(
                    "Rank",
                    help="Posição do candidato. Rank 1 = mais provável para este composto.",
                ),
            },
        )

        # --- Pontuação de identificação (ranking) ---
        st.markdown("**Pontuação de identificação**")
        st.caption(
            "Score final que determina o ranking dos candidatos. "
            "Calculado a partir dos dados instrumentais — pesos provisórios, calibráveis pelo IST."
        )

        colunas_score = ["Candidato", "Score Massa", score_col, "Score Qualidade Dados", "Rank"]
        colunas_score_presentes = [c for c in colunas_score if c in df_detalhe.columns]
        st.dataframe(
            df_detalhe[colunas_score_presentes],
            use_container_width=True,
            hide_index=True,
            column_config={
                "Candidato": st.column_config.TextColumn("Candidato molecular"),
                score_col: st.column_config.ProgressColumn(
                    "Pontuação de identificação",
                    help="Score final (0–100) que determina o ranking dos candidatos deste composto.",
                    min_value=0, max_value=100, format="%.1f",
                ),
                "Score Qualidade Dados": st.column_config.ProgressColumn(
                    "Dados externos disponíveis",
                    help="% de metadados encontrados em bases públicas (PubChem, ChEBI). Não entra no ranking.",
                    min_value=0, max_value=100, format="%.0f%%",
                ),
                "Score Massa": st.column_config.NumberColumn(
                    "Pontuação de massa",
                    help="Pontuação do erro de massa (0–40): máximo quando erro ≤ 5 ppm, zero quando ≥ 20 ppm.",
                    format="%.2f",
                ),
                "Rank": st.column_config.NumberColumn(
                    "Rank",
                    help="Rank 1 = candidato mais provável para este composto.",
                ),
            },
        )

        # Gráfico comparativo
        if len(df_detalhe) > 1:
            cols_grafico = [
                c for c in ["Score Fragmentacao", "Score Lab", "Isotope Similarity"]
                if c in df_detalhe.columns
            ]
            if cols_grafico:
                st.markdown("**Comparativo dos scores instrumentais entre candidatos**")
                st.caption("Componentes individuais da identificação — úteis para comparar candidatos com pontuação similar.")
                try:
                    st.bar_chart(
                        df_detalhe.set_index("Candidato")[cols_grafico],
                        use_container_width=True,
                    )
                except Exception:
                    pass

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption("Omics ETL Pipeline · IST Ambiental / SENAI")
