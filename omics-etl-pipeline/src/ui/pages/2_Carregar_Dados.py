"""
Página: Carregar Dados
Upload de novos experimentos e execução manual do pipeline ETL.
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
    page_title="Carregar Dados | Omics ETL",
    page_icon="📤",
    layout="wide",
)

st.title("📤 Carregar Novo Experimento")
st.caption("Envie os arquivos de identificação e abundância para processamento.")
st.divider()

# ---------------------------------------------------------------------------
# Seção de ajuda — colapsada por padrão para não poluir o fluxo principal
# ---------------------------------------------------------------------------
with st.expander("ℹ️ Como preparar os arquivos para upload", expanded=False):
    col_h1, col_h2 = st.columns(2)

    with col_h1:
        st.markdown(
            """
            **Arquivo de Identificação** *(ex.: `IDENTIFICACAO.xlsx`)*

            Exportado diretamente do software do equipamento LC-MS/MS.
            Colunas **obrigatórias**:

            | Coluna | Descrição |
            |---|---|
            | `Compound` | Código único do sinal analítico |
            | `Description` | Nome do candidato molecular |

            Colunas **opcionais** (melhoram o ranking quando presentes):

            `Score`, `Mass Error (ppm)`, `Isotope Similarity`,
            `Adducts`, `Neutral mass (Da)`, `Fragmentation score`
            """
        )

    with col_h2:
        st.markdown(
            """
            **Arquivo de Abundância** *(ex.: `ABUND.xlsx`)*

            Contém as intensidades dos sinais medidos pelo instrumento.
            Colunas **obrigatórias**:

            | Coluna | Descrição |
            |---|---|
            | `Compound` | Código do sinal — deve ser idêntico ao arquivo de Identificação |
            | `m/z` | Razão massa/carga medida |

            > Os valores de `Compound` são usados para cruzar as duas planilhas.
            > Verifique se ambos os arquivos pertencem ao **mesmo experimento**
            > antes de fazer o upload.
            """
        )

st.divider()

# ---------------------------------------------------------------------------
# Etapa 1 — Upload dos arquivos
# ---------------------------------------------------------------------------
st.subheader("Etapa 1 — Selecionar arquivos")

col_ident, col_abund = st.columns(2)

with col_ident:
    st.markdown("**Arquivo de Identificação**")
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
    st.markdown("**Arquivo de Abundância**")
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
# Etapa 2 — Validação e preview (automáticos quando ambos estão presentes)
# ---------------------------------------------------------------------------
validacao_ok = False

if arquivo_ident and arquivo_abund:
    st.divider()
    st.subheader("Etapa 2 — Validação")

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
                f"✅ **{arquivo_ident.name}** e **{arquivo_abund.name}** validados com sucesso — "
                "arquivos compatíveis e prontos para processamento."
            )
        except BatchValidacaoError as e:
            st.error(f"❌ **Validação falhou**\n\n{e}")

    # Preview das primeiras linhas (lido direto dos bytes — sem depender do tempdir)
    if validacao_ok:
        with st.expander("Preview — primeiras 5 linhas do arquivo de identificação", expanded=False):
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
                st.warning(f"Não foi possível gerar preview: {e}")

# ---------------------------------------------------------------------------
# Etapa 3 — Execução
# ---------------------------------------------------------------------------
if arquivo_ident and arquivo_abund:
    st.divider()
    st.subheader("Etapa 3 — Processamento")

    btn_disabled = not validacao_ok
    btn_help     = "Corrija os erros de validação antes de processar." if btn_disabled else None

    if st.button("🚀 Iniciar Processamento", type="primary", disabled=btn_disabled, help=btn_help):
        resultado = None

        with st.status("Processando experimento...", expanded=True) as status:
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    tmp     = Path(tmpdir)
                    p_ident = tmp / arquivo_ident.name
                    p_abund = tmp / arquivo_abund.name

                    st.write("Preparando arquivos temporários...")
                    p_ident.write_bytes(arquivo_ident.getvalue())
                    p_abund.write_bytes(arquivo_abund.getvalue())

                    job = PipelineJob(
                        caminho_ident=p_ident,
                        caminho_abund=p_abund,
                        fonte="upload_manual",
                        nome_ident=arquivo_ident.name,
                        nome_abund=arquivo_abund.name,
                    )

                    st.write("Executando pipeline (Extract → Transform → API → Load)...")
                    st.caption("Esta etapa pode levar alguns minutos dependendo do número de moléculas novas.")

                    batch_id_resultado = executar_pipeline_com_job(job)

                if batch_id_resultado is not None:
                    status.update(label="Processamento concluído!", state="complete")
                    resultado = {"tipo": "sucesso", "batch_id": batch_id_resultado}
                else:
                    status.update(label="Pipeline não concluído", state="error")
                    resultado = {"tipo": "erro", "msg": "O pipeline não foi concluído com sucesso. Verifique se os arquivos estão corretos e tente novamente."}

            except BatchDuplicadoError as e:
                status.update(label="Arquivos já processados anteriormente", state="complete")
                resultado = {"tipo": "duplicado", "batch_id": e.batch_id}

            except Exception as e:
                status.update(label="Erro inesperado", state="error")
                msg = str(e)
                # Garante mensagem legível mesmo para erros técnicos longos
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
            f"**ℹ️ Estes arquivos já foram processados anteriormente**\n\n"
            f"Este par de arquivos é idêntico ao **Batch #{bid}**, já registrado com sucesso. "
            "Os dados estão disponíveis no banco — nenhuma ação necessária."
        )
        col_a, col_b, _ = st.columns([2, 2, 4])
        if bid and col_a.button(f"→ Ver Ranking do Batch #{bid}", type="primary"):
            st.session_state["ir_para_batch"] = bid
            del st.session_state["resultado_upload"]
            st.switch_page("app.py")
        if col_b.button("Carregar outros arquivos"):
            del st.session_state["resultado_upload"]
            st.rerun()

    elif res.get("tipo") == "sucesso":
        bid = res["batch_id"]

        # Carrega estatísticas do batch recém-criado
        try:
            info = next((b for b in listar_batches() if b["id"] == bid), None)
        except Exception:
            info = None

        st.success(f"✅ **Processamento concluído — Batch #{bid}**")

        if info:
            m1, m2, m3 = st.columns(3)
            m1.metric("Sinais",                   info.get("total_sinais")        or "—")
            m2.metric("Candidatos",               info.get("total_candidatos")    or "—")
            m3.metric("Novas moléculas (API)",    info.get("total_moleculas_api") or "—")

        col_a, col_b, _ = st.columns([2, 2, 4])
        if col_a.button(f"→ Ver Ranking do Batch #{bid}", type="primary"):
            st.session_state["ir_para_batch"] = bid
            del st.session_state["resultado_upload"]
            st.switch_page("app.py")
        if col_b.button("Processar outro experimento"):
            del st.session_state["resultado_upload"]
            st.rerun()

    else:
        msg = res.get("msg", "Erro desconhecido.")
        st.error(f"❌ **Processamento falhou**\n\n{msg}")
        if st.button("Tentar com outros arquivos"):
            del st.session_state["resultado_upload"]
            st.rerun()
