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
from src.reports.pdf_analitico import gerar_relatorio_analitico
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
# Descrição do relatório disponível
# ---------------------------------------------------------------------------
st.subheader("Tipo de relatório")

col_tipo, col_desc = st.columns([1, 2])

with col_tipo:
    with st.container(border=True):
        st.markdown("### 📊 Relatório Analítico")
        st.markdown("**Disponível**")
        st.caption(
            "Documento completo para revisão técnica e reuniões com o IST. "
            "Inclui métricas, gráficos, tabela de resultados e nota metodológica."
        )

with col_desc:
    with st.container(border=True):
        st.markdown("**Conteúdo do relatório:**")
        st.markdown(
            "- Resumo do experimento (compostos, candidatos, score médio, empates)  \n"
            "- Leitura rápida — insights automáticos sobre confiança e ambiguidade  \n"
            "- Gráfico de discriminabilidade (critérios de desempate IST)  \n"
            "- Distribuição dos scores de identificação (Rank 1)  \n"
            "- Perfil químico — classes ChEBI dos candidatos mais prováveis  \n"
            "- Tabela completa de Rank 1 por composto (ordenada por incerteza)  \n"
            "- Detalhamento dos compostos em empate (se houver)  \n"
            "- Nota metodológica e disclaimer de validação"
        )
        st.caption(
            "Formato A4 · Multi-página · Sem interatividade · "
            "Pronto para impressão ou distribuição digital."
        )

    # Nota sobre o que NÃO está disponível na v1
    with st.expander("Outros tipos de relatório (em desenvolvimento)"):
        st.markdown(
            "**Relatório Executivo** — versão simplificada de 1–2 páginas para gestores, "
            "sem scores técnicos detalhados. *(v2)*  \n\n"
            "**Relatório Cross-batch** — comparação entre dois experimentos. *(v2)*  \n\n"
            "**Lista de Revisão** — PDF com campos para anotação manual pelo especialista. *(v2)*"
        )

st.divider()

# ---------------------------------------------------------------------------
# Geração do PDF — com persistência de estado para o download_button
# ---------------------------------------------------------------------------
_STATE_KEY_BYTES    = "pdf_bytes_v1"
_STATE_KEY_BATCH    = "pdf_batch_id_v1"
_STATE_KEY_FILENAME = "pdf_filename_v1"

# Invalida cache se a análise mudou
if st.session_state.get(_STATE_KEY_BATCH) != batch_id_real:
    st.session_state[_STATE_KEY_BYTES]    = None
    st.session_state[_STATE_KEY_BATCH]    = None
    st.session_state[_STATE_KEY_FILENAME] = None

st.subheader("Gerar relatório")

col_btn, col_status = st.columns([1, 2])

with col_btn:
    _gerar = st.button(
        "📄 Gerar Relatório Analítico",
        type="primary",
        use_container_width=True,
        help="Processa os dados e monta o PDF em memória. Pode levar alguns segundos.",
    )

if _gerar:
    with st.spinner("Gerando relatório... isso pode levar alguns segundos."):
        try:
            ins           = computar_insights(df)
            cobertura_ext = carregar_cobertura_externa(batch_id_real) if batch_id_real else {}
            pdf_bytes     = gerar_relatorio_analitico(ins, batch_info, cobertura_ext)

            bid_str  = f"batch{batch_id_real}" if batch_id_real else "recente"
            filename = f"relatorio_analitico_{bid_str}.pdf"

            st.session_state[_STATE_KEY_BYTES]    = pdf_bytes
            st.session_state[_STATE_KEY_BATCH]    = batch_id_real
            st.session_state[_STATE_KEY_FILENAME] = filename

        except Exception as exc:
            st.error(
                f"Erro ao gerar o relatório:  \n`{exc}`  \n\n"
                "Verifique se os dados do experimento estão íntegros e tente novamente."
            )

# Exibe download_button quando o PDF estiver disponível
_pdf_bytes = st.session_state.get(_STATE_KEY_BYTES)
_filename  = st.session_state.get(_STATE_KEY_FILENAME, "relatorio.pdf")

if _pdf_bytes:
    with col_status:
        st.success(
            f"Relatório gerado com sucesso — **{len(_pdf_bytes) / 1024:.0f} KB**  \n"
            "Clique no botão abaixo para baixar."
        )

    st.download_button(
        label="⬇ Baixar PDF",
        data=_pdf_bytes,
        file_name=_filename,
        mime="application/pdf",
        type="primary",
        use_container_width=False,
    )

    # Prévia de métricas do relatório gerado
    ins = computar_insights(df)
    if ins:
        st.divider()
        st.markdown("**Conteúdo incluído no relatório:**")
        _c1, _c2, _c3, _c4 = st.columns(4)
        _c1.metric("Compostos", ins["n_compostos"])
        _c2.metric("Candidatos", ins["n_candidatos_tot"])
        _c3.metric(
            "Em empate",
            ins["n_empates"] if ins["_tem_empate"] else "—",
        )
        _c4.metric("Score médio Rank 1", f"{ins['mean_pontuacao']:.1f}")

# ---------------------------------------------------------------------------
# Rodapé
# ---------------------------------------------------------------------------
st.divider()
st.caption(
    "Omics ETL Pipeline · IST Ambiental / SENAI  ·  "
    "Os relatórios gerados são para uso interno e requerem validação do especialista analítico."
)
