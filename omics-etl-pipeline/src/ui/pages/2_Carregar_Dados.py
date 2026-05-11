"""
Página: Nova Análise
Upload de novos experimentos e execução do processamento.
"""
import io
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_ROOT))

from src.etl.job import PipelineJob
from src.etl.validate import BatchDuplicadoError, BatchValidacaoError, validar_arquivos_entrada
from src.pipeline import executar_pipeline_com_job
from src.ui.utils import listar_batches

st.set_page_config(
    page_title="Nova Análise | Omics ETL",
    page_icon="📤",
    layout="wide",
)

st.title("📤 Nova Análise")
st.caption("Envie as planilhas exportadas pelo instrumento para iniciar o processamento.")
st.divider()

# ---------------------------------------------------------------------------
# Seção de ajuda — colapsada por padrão para não poluir o fluxo principal
# ---------------------------------------------------------------------------
with st.expander("ℹ️ Como preparar as planilhas para envio", expanded=False):
    col_h1, col_h2 = st.columns(2)

    with col_h1:
        st.markdown(
            """
            **Planilha de identificação** *(ex.: `IDENTIFICACAO.xlsx`)*

            Exportada pelo software do equipamento LC-MS/MS
            (ex.: MassHunter, Progenesis, MetaboScape).
            Contém os candidatos moleculares sugeridos para cada sinal detectado.

            Colunas **obrigatórias**:

            | Coluna | Descrição |
            |---|---|
            | `Compound` | Código único do sinal analítico |
            | `Description` | Nome do candidato molecular |

            Colunas **opcionais** (melhoram a pontuação quando presentes):

            `Score`, `Mass Error (ppm)`, `Isotope Similarity`,
            `Adducts`, `Neutral mass (Da)`, `Fragmentation score`
            """
        )

    with col_h2:
        st.markdown(
            """
            **Planilha de abundâncias** *(ex.: `ABUND.xlsx`)*

            Exportada pelo software do equipamento.
            Contém a intensidade de cada sinal detectado na amostra.

            Colunas **obrigatórias**:

            | Coluna | Descrição |
            |---|---|
            | `Compound` | Código do sinal — deve ser idêntico à planilha de identificação |
            | `m/z` | Razão massa/carga medida pelo instrumento |

            > Os valores de `Compound` cruzam as duas planilhas.
            > Verifique se ambas pertencem ao **mesmo experimento**
            > antes de enviar.
            """
        )

st.divider()

# ---------------------------------------------------------------------------
# Etapa 1 — Seleção das planilhas
# ---------------------------------------------------------------------------
st.subheader("Etapa 1 — Selecionar planilhas")

col_ident, col_abund = st.columns(2)

with col_ident:
    st.markdown("**Planilha de identificação**")
    st.caption("Exportada do software do instrumento — contém os candidatos e scores de identificação")
    arquivo_ident = st.file_uploader(
        "ident_upload",
        type=["xlsx", "xlsm", "xls", "csv"],
        label_visibility="collapsed",
        key="upload_ident",
    )
    if arquivo_ident:
        tam = arquivo_ident.size
        tam_fmt = f"{tam / (1024*1024):.1f} MB" if tam >= 1024*1024 else f"{tam // 1024} KB"
        st.caption(f"✅ {arquivo_ident.name} ({tam_fmt})")
    else:
        st.caption("Formatos aceitos: .xlsx, .xlsm, .xls, .csv · Máx. 50 MB")

with col_abund:
    st.markdown("**Planilha de abundâncias**")
    st.caption("Exportada do software do instrumento — contém os sinais e valores de m/z medidos")
    arquivo_abund = st.file_uploader(
        "abund_upload",
        type=["xlsx", "xlsm", "xls", "csv"],
        label_visibility="collapsed",
        key="upload_abund",
    )
    if arquivo_abund:
        tam = arquivo_abund.size
        tam_fmt = f"{tam / (1024*1024):.1f} MB" if tam >= 1024*1024 else f"{tam // 1024} KB"
        st.caption(f"✅ {arquivo_abund.name} ({tam_fmt})")
    else:
        st.caption("Formatos aceitos: .xlsx, .xlsm, .xls, .csv · Máx. 50 MB")

# ---------------------------------------------------------------------------
# Etapa 2 — Verificação dos arquivos (automática quando ambos estão presentes)
# ---------------------------------------------------------------------------
validacao_ok = False

if arquivo_ident and arquivo_abund:
    st.divider()
    st.subheader("Etapa 2 — Verificação dos arquivos")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        p_ident = tmp / arquivo_ident.name
        p_abund = tmp / arquivo_abund.name
        p_ident.write_bytes(arquivo_ident.getvalue())
        p_abund.write_bytes(arquivo_abund.getvalue())

        try:
            validar_arquivos_entrada(p_ident, p_abund)
            validacao_ok = True
            st.success(
                f"✅ **{arquivo_ident.name}** e **{arquivo_abund.name}** verificados com sucesso — "
                "as planilhas são compatíveis e estão prontas para processamento."
            )
        except BatchValidacaoError as e:
            st.error(f"❌ **Verificação falhou**\n\n{e}")

    # Preview das primeiras linhas
    if validacao_ok:
        with st.expander("Pré-visualização — primeiras 5 linhas da planilha de identificação", expanded=False):
            try:
                suf = Path(arquivo_ident.name).suffix.lower()
                bytes_ident = io.BytesIO(arquivo_ident.getvalue())
                if suf in (".xlsx", ".xlsm"):
                    df_prev = pd.read_excel(bytes_ident, engine="openpyxl", nrows=5)
                elif suf == ".xls":
                    df_prev = pd.read_excel(bytes_ident, nrows=5)
                else:
                    df_prev = pd.read_csv(bytes_ident, encoding="latin1", sep=";", nrows=5)
                st.dataframe(df_prev, use_container_width=True, hide_index=True)
            except Exception as e:
                st.warning(f"Não foi possível gerar pré-visualização: {e}")

# ---------------------------------------------------------------------------
# Etapa 3 — Processamento
# ---------------------------------------------------------------------------
if arquivo_ident and arquivo_abund:
    st.divider()
    st.subheader("Etapa 3 — Processar experimento")

    btn_disabled = not validacao_ok
    btn_help     = "Corrija os problemas de verificação antes de processar." if btn_disabled else None

    if st.button("🚀 Iniciar Análise", type="primary", disabled=btn_disabled, help=btn_help):
        resultado = None

        with st.status("Processando experimento...", expanded=True) as status:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp     = Path(tmpdir)
                    p_ident = tmp / arquivo_ident.name
                    p_abund = tmp / arquivo_abund.name

                    st.write("Preparando os dados...")
                    p_ident.write_bytes(arquivo_ident.getvalue())
                    p_abund.write_bytes(arquivo_abund.getvalue())

                    job = PipelineJob(
                        caminho_ident=p_ident,
                        caminho_abund=p_abund,
                        fonte="upload_manual",
                        nome_ident=arquivo_ident.name,
                        nome_abund=arquivo_abund.name,
                    )

                    st.write("Identificando candidatos moleculares e calculando pontuações...")
                    st.caption(
                        "Esta etapa pode levar alguns minutos. "
                        "O sistema está consultando bases de dados científicas (PubChem, ChEBI) "
                        "para enriquecer as informações dos candidatos identificados."
                    )

                    batch_id_resultado = executar_pipeline_com_job(job)

                if batch_id_resultado is not None:
                    status.update(label="Análise concluída!", state="complete")
                    resultado = {"tipo": "sucesso", "batch_id": batch_id_resultado}
                else:
                    status.update(label="Processamento não concluído", state="error")
                    resultado = {
                        "tipo": "erro",
                        "msg": "O processamento não foi concluído com sucesso. Verifique se os arquivos estão corretos e tente novamente.",
                    }

            except BatchDuplicadoError as e:
                status.update(label="Planilhas já analisadas anteriormente", state="complete")
                resultado = {"tipo": "duplicado", "batch_id": e.batch_id}

            except Exception as e:
                status.update(label="Erro inesperado", state="error")
                msg = str(e)
                if len(msg) > 500:
                    msg = msg[:500] + "..."
                resultado = {"tipo": "erro", "msg": msg}

        if resultado:
            st.session_state["resultado_upload"] = resultado
            st.rerun()

# ---------------------------------------------------------------------------
# Exibição do resultado (persiste entre reruns via session_state)
# ---------------------------------------------------------------------------
if "resultado_upload" in st.session_state:
    res = st.session_state["resultado_upload"]
    st.divider()

    if res.get("tipo") == "duplicado":
        bid = res.get("batch_id")
        st.info(
            f"**ℹ️ Estas planilhas já foram analisadas anteriormente**\n\n"
            f"Este par de arquivos é idêntico à **Análise #{bid}**, já registrada com sucesso. "
            "Os resultados estão disponíveis — nenhum reprocessamento é necessário."
        )
        col_a, col_b, _ = st.columns([2, 2, 4])
        if bid and col_a.button(f"→ Ver resultados da Análise #{bid}", type="primary"):
            st.session_state["ir_para_batch"] = bid
            del st.session_state["resultado_upload"]
            st.switch_page("app.py")
        if col_b.button("Enviar outras planilhas"):
            del st.session_state["resultado_upload"]
            st.rerun()

    elif res.get("tipo") == "sucesso":
        bid = res["batch_id"]

        try:
            info = next((b for b in listar_batches() if b["id"] == bid), None)
        except Exception:
            info = None

        st.success(f"✅ **Análise concluída — Experimento #{bid}**")

        if info:
            m1, m2, m3 = st.columns(3)
            m1.metric(
                "Compostos detectados",
                info.get("total_sinais") or "—",
                help="Sinais analíticos únicos processados nesta análise",
            )
            m2.metric(
                "Candidatos identificados",
                info.get("total_candidatos") or "—",
                help="Total de candidatos moleculares para todos os compostos detectados",
            )
            m3.metric(
                "Moléculas buscadas online",
                info.get("total_moleculas_api") or "—",
                help="Compostos consultados em PubChem e ChEBI para enriquecimento de dados",
            )

        col_a, col_b, _ = st.columns([2, 2, 4])
        if col_a.button(f"→ Ver resultados da Análise #{bid}", type="primary"):
            st.session_state["ir_para_batch"] = bid
            del st.session_state["resultado_upload"]
            st.switch_page("app.py")
        if col_b.button("Processar outro experimento"):
            del st.session_state["resultado_upload"]
            st.rerun()

    else:
        msg = res.get("msg", "Erro desconhecido.")
        st.error(f"❌ **Processamento falhou**\n\n{msg}")
        if st.button("Tentar com outras planilhas"):
            del st.session_state["resultado_upload"]
            st.rerun()
