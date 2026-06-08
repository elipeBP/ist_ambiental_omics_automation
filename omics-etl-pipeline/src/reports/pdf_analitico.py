"""
Relatório Analítico v2 — Omics ETL Pipeline.

Fluxo de dados:
  computar_insights(df) → ins
  gerar_narrativa(ins, cobertura_ext) → nar   [chamado internamente]
  gerar_relatorio_analitico(ins, batch_info, cobertura_ext) → bytes PDF

Seções:
  P1 — Status da análise · Métricas de ação · Diagnóstico automático · Ações recomendadas
  P2 — Compostos prioritários para revisão + Detalhe dos empates
  P3 — Perfil químico + Evidências técnicas (scores · critérios)
  P4 — Apêndice — Nota metodológica

Dependências permitidas:
  pdf_analitico → _shared (layout) · narrative (interpretação) · charts (gráficos)
  NÃO importa diretamente: streamlit · insights (via narrative/shared)
"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd

from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Table,
    TableStyle,
)

from src.reports import charts as _charts
from src.reports._shared import (
    AMARELO_CELL,
    AZUL_IST,
    CINZA_CLARO,
    CINZA_TBL,
    MARGIN_B,
    MARGIN_L,
    MARGIN_R,
    MARGIN_T,
    USABLE_W,
    VERDE_CELL,
    VERMELHO_CELL,
    build_empate_subtable,
    embed_chart,
    hr,
    insight_para,
    make_header_footer,
    make_styles,
    score_cell_color,
    spacer,
    status_badge_block,
    trunc,
)
from src.reports.narrative import gerar_narrativa


# ---------------------------------------------------------------------------
# Mapeamento prioridade → label PDF + cores de célula
# ---------------------------------------------------------------------------

_PRIORITY_LABEL: dict[str, str] = {
    "🔴 Alta":  "Alta",
    "🟡 Média": "Média",
    "—":        "—",
    "✅ OK":    "OK",
}

_PRIORITY_BG: dict[str, HexColor] = {
    "Alta":  VERMELHO_CELL,
    "Média": AMARELO_CELL,
    "—":     white,
    "OK":    VERDE_CELL,
}

_PRIORITY_FG: dict[str, str] = {
    "Alta":  "#8b0000",
    "Média": "#7a4000",
    "—":     "#666666",
    "OK":    "#1b4f2a",
}

# Remove emoji e variantes Unicode — necessário para Helvetica no ReportLab
_RE_EMOJI = re.compile(
    "["
    "\U0001F300-\U0001FFFF"   # Misc symbols, emoticons, pictographs
    "☀-➿"            # Misc symbols, dingbats (inclui ✅ ⚠️)
    "︀-️"            # Variation selectors
    "‍"                   # ZWJ
    "]+",
    flags=re.UNICODE,
)


def _strip_emoji(text: str) -> str:
    """Remove emoji — aplicado em Prioridade e Situação para compatibilidade Helvetica."""
    if not isinstance(text, str):
        return str(text) if text is not None else "—"
    result = _RE_EMOJI.sub("", text).strip()
    return result if result else "—"


# ---------------------------------------------------------------------------
# Larguras das colunas da tabela de prioridades (em pontos)
# ---------------------------------------------------------------------------

_W_PRIO      = 52.0   # Prioridade
_W_COMPOSTO  = 70.0   # Composto (sinal m/z)
_W_CONFIANCA = 48.0   # Confiança (score numérico)
_W_CATEGORIA = 75.0   # Categoria (opcional — presente só se na priority_df)
_W_SITUACAO  = 100.0  # Situação
# Candidato mais provável = USABLE_W − soma das demais


# ---------------------------------------------------------------------------
# Seção 1 — Status da análise
# ---------------------------------------------------------------------------

def _sec_status(nar: dict, styles: dict) -> list:
    """Badge de status + parágrafo técnico + frase de conclusão."""
    badge_label = nar["status_label"].upper()
    badge = status_badge_block(nar["status_cor"], badge_label, styles)

    para_rl   = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", nar["paragrafo"])
    concl_rl  = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", nar["conclusao"])

    return [
        KeepTogether([
            badge,
            spacer(0.2),
            Paragraph(para_rl,  styles["Body"]),
            Paragraph(concl_rl, styles["Body"]),
        ]),
    ]


# ---------------------------------------------------------------------------
# Seção 2 — Métricas de ação (3 cards)
# ---------------------------------------------------------------------------

def _sec_metricas_acao(nar: dict, ins: dict, styles: dict) -> list:
    """Tabela 2×3: n_revisar / n_alta_conf / risco_label."""
    n_revisar = nar["n_revisar"]
    n_alta    = ins.get("n_alta_conf", 0)
    n_comp    = ins.get("n_compostos", 1) or 1
    risco     = nar["risco_label"]

    pct_alta = f" ({n_alta / n_comp * 100:.0f}%)" if n_comp else ""

    data = [
        [
            Paragraph(str(n_revisar),          styles["MetricValue"]),
            Paragraph(f"{n_alta}{pct_alta}",    styles["MetricValue"]),
            Paragraph(risco,                    styles["MetricValue"]),
        ],
        [
            Paragraph("Para revisão",           styles["MetricLabel"]),
            Paragraph("Alta confiança",         styles["MetricLabel"]),
            Paragraph("Risco analítico",        styles["MetricLabel"]),
        ],
    ]

    col_w = USABLE_W / 3
    tbl = Table(data, colWidths=[col_w] * 3)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), CINZA_CLARO),
        ("BACKGROUND",    (0, 1), (-1, 1), white),
        ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#d0d8e0")),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, HexColor("#dce3ea")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [tbl]


# ---------------------------------------------------------------------------
# Seção 3 — Diagnóstico automático
# ---------------------------------------------------------------------------

def _sec_diagnostico(nar: dict, styles: dict) -> list:
    """Tabela dimensional 3 colunas × N linhas — alimentada por nar['dimensoes']."""
    dimensoes = nar.get("dimensoes", [])
    if not dimensoes:
        return [Paragraph("Sem dimensões diagnósticas disponíveis.", styles["Body"])]

    col_dim    = USABLE_W * 0.34
    col_val    = USABLE_W * 0.22
    col_interp = USABLE_W - col_dim - col_val

    _val_style = ParagraphStyle(
        "DiagVal",
        parent=styles["TableCell"],
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )

    header_row = [
        Paragraph("Dimensão",      styles["TableHeader"]),
        Paragraph("Valor",         styles["TableHeader"]),
        Paragraph("Interpretação", styles["TableHeader"]),
    ]
    rows = [header_row]
    for label, valor, interp in dimensoes:
        rows.append([
            Paragraph(str(label), styles["TableCell"]),
            Paragraph(str(valor), _val_style),
            Paragraph(str(interp), styles["TableCell"]),
        ])

    tbl = Table(rows, colWidths=[col_dim, col_val, col_interp], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), AZUL_IST),
        ("TEXTCOLOR",      (0, 0), (-1, 0), white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_TBL]),
        ("GRID",           (0, 0), (-1, -1), 0.25, HexColor("#d0d0d0")),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 5),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",          (0, 0), (-1, 0),  "CENTER"),
    ]))
    return [KeepTogether([tbl])]


# ---------------------------------------------------------------------------
# Seção 4 — Ações recomendadas (bullets coloridos)
# ---------------------------------------------------------------------------

def _sec_acoes(ins: dict, styles: dict) -> list:
    """Bullets de insight coloridos por tipo (success / warning / info)."""
    return [insight_para(tipo, texto, styles) for tipo, texto in ins.get("insights", [])]


# ---------------------------------------------------------------------------
# Seção 5 — Compostos prioritários para revisão
# ---------------------------------------------------------------------------

def _build_priority_pdf_table(
    priority_df: pd.DataFrame,
    styles: dict,
) -> Table:
    """
    Constrói ReportLab Table a partir do priority_df da camada narrative.

    Estratégia de emoji:
      Coluna Prioridade — mapeada via _PRIORITY_LABEL + cor de célula (_PRIORITY_BG)
      Coluna Situação   — _strip_emoji() para segurança futura
    """
    has_cat = "Categoria" in priority_df.columns

    fixed_w = _W_PRIO + _W_COMPOSTO + _W_CONFIANCA + _W_SITUACAO
    if has_cat:
        fixed_w += _W_CATEGORIA
    col_w_cand = max(USABLE_W - fixed_w, 80.0)

    col_widths = [_W_PRIO, _W_COMPOSTO, _W_CONFIANCA]
    headers    = ["Prioridade", "Composto", "Confiança"]
    if has_cat:
        col_widths.append(_W_CATEGORIA)
        headers.append("Categoria")
    col_widths += [_W_SITUACAO, col_w_cand]
    headers    += ["Situação", "Candidato mais provável"]

    _center = ParagraphStyle("PriorCenter", parent=styles["TableCell"], alignment=TA_CENTER)
    _center_bold = ParagraphStyle(
        "PriorCenterBold", parent=styles["TableCell"],
        alignment=TA_CENTER, fontName="Helvetica-Bold",
    )

    header_row = [Paragraph(h, styles["TableHeader"]) for h in headers]
    rows = [header_row]
    cell_styles: list[tuple] = []

    for row_i, (_, row) in enumerate(priority_df.iterrows(), start=1):
        # Prioridade — strip emoji + cor
        prio_raw  = str(row.get("Prioridade", "—"))
        prio_lbl  = _PRIORITY_LABEL.get(prio_raw, _strip_emoji(prio_raw)) or "—"
        prio_bg   = _PRIORITY_BG.get(prio_lbl, white)
        prio_fg   = _PRIORITY_FG.get(prio_lbl, "#444444")
        _prio_s   = ParagraphStyle(
            f"PrioLbl{row_i}", parent=styles["TableCell"],
            alignment=TA_CENTER, fontName="Helvetica-Bold",
            textColor=HexColor(prio_fg),
        )
        cell_styles.append(("BACKGROUND", (0, row_i), (0, row_i), prio_bg))

        # Composto
        composto = trunc(str(row.get("Composto", "—")), 22)

        # Confiança — cor por tier
        conf_val = row.get("Confiança")
        try:
            conf_str   = f"{float(conf_val):.1f}" if pd.notna(conf_val) else "—"
            conf_color = score_cell_color(conf_val)
        except (TypeError, ValueError):
            conf_str   = "—"
            conf_color = white
        cell_styles.append(("BACKGROUND", (2, row_i), (2, row_i), conf_color))

        # Situação — strip emoji (preparado para valores futuros com emoji)
        situacao = _strip_emoji(str(row.get("Situação", "—")))

        # Candidato
        candidato = trunc(str(row.get("Candidato mais provável", "—")), 42)

        data_row = [
            Paragraph(prio_lbl,  _prio_s),
            Paragraph(composto,  styles["TableCell"]),
            Paragraph(conf_str,  _center_bold),
        ]
        if has_cat:
            data_row.append(Paragraph(trunc(str(row.get("Categoria", "—")), 22), styles["TableCell"]))
        data_row += [
            Paragraph(situacao,  styles["TableCell"]),
            Paragraph(candidato, styles["TableCell"]),
        ]
        rows.append(data_row)

    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    ts = TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), AZUL_IST),
        ("TEXTCOLOR",      (0, 0), (-1, 0), white),
        ("FONTNAME",       (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_TBL]),
        ("GRID",           (0, 0), (-1, -1), 0.25, HexColor("#cccccc")),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("LEFTPADDING",    (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ])
    for cmd in cell_styles:
        ts.add(*cmd)
    tbl.setStyle(ts)
    return tbl


def _sec_compostos_prioritarios(nar: dict, ins: dict, styles: dict) -> list:
    """Tabela de prioridades de revisão construída a partir de nar['priority_df']."""
    priority_df = nar.get("priority_df", pd.DataFrame())
    if priority_df.empty:
        return [Paragraph("Sem compostos identificados nesta análise.", styles["Body"])]

    tbl = _build_priority_pdf_table(priority_df, styles)
    n   = len(priority_df)
    cap = (
        f"{n} compostos ordenados por prioridade de revisão. "
        "Alta = empate ativo (revisão obrigatória) · "
        "Média = baixa confiança · OK = identificação segura."
    )
    return [tbl, spacer(0.15), Paragraph(cap, styles["Caption"])]


# ---------------------------------------------------------------------------
# Seção 6 — Detalhe dos compostos em empate
# ---------------------------------------------------------------------------

def _sec_empates_detalhe(ins: dict, styles: dict) -> list:
    """Subtabelas detalhadas por composto em empate — reusa _shared.build_empate_subtable."""
    if not ins.get("_tem_empate", False) or ins.get("n_empates", 0) == 0:
        return []

    rank1_df   = ins["rank1_df"]
    score_col  = ins["score_col"]
    emp_sinais = ins.get("emp_sinais", frozenset())
    n_emp      = len(emp_sinais)

    elems: list = [
        Paragraph(
            f"Os {n_emp} compostos abaixo possuem dois ou mais candidatos com "
            "identificação automaticamente indistinguível (mesmos scores em todos os critérios). "
            "A decisão do candidato definitivo requer avaliação pelo especialista analítico.",
            styles["Body"],
        ),
        spacer(0.3),
    ]

    for sinal in sorted(emp_sinais):
        grupo = rank1_df[rank1_df["Sinal"] == sinal].copy()
        if grupo.empty:
            continue
        elems.append(KeepTogether([
            Paragraph(f"<b>{sinal}</b>", styles["SubSection"]),
            build_empate_subtable(grupo, score_col, styles),
            spacer(0.2),
        ]))

    return elems


# ---------------------------------------------------------------------------
# Seção 7 — Perfil químico
# ---------------------------------------------------------------------------

def _sec_perfil_quimico(ins: dict, cobertura_ext: dict, styles: dict) -> list:
    """Gráfico de categorias químicas + linha de cobertura ChEBI / PubChem."""
    classes_df = ins.get("classes_classif", pd.DataFrame())
    if classes_df.empty:
        return []

    elems: list = []
    result = _charts.chart_classes(classes_df)
    img    = embed_chart(result)
    if img:
        elems.append(img)
        n_comp    = ins.get("n_compostos", 0)
        n_classif = ins.get("n_classif", 0)
        n_nc      = ins.get("n_nc", 0)
        elems.append(Paragraph(
            f"Categorias químicas dos candidatos Rank 1. "
            f"{n_classif} de {n_comp} compostos classificados · {n_nc} sem classificação.",
            styles["Caption"],
        ))

    if cobertura_ext:
        pct_ch  = cobertura_ext.get("pct_chebi", 0)
        pct_pub = cobertura_ext.get("pct_pubchem", 0)
        if pct_ch or pct_pub:
            elems.append(spacer(0.15))
            elems.append(Paragraph(
                f"Cobertura de bases externas (Rank 1): "
                f"<b>ChEBI {pct_ch:.0f}%</b>  ·  <b>PubChem {pct_pub:.0f}%</b>",
                styles["Body"],
            ))

    return elems


# ---------------------------------------------------------------------------
# Seção 8 — Evidências técnicas
# ---------------------------------------------------------------------------

def _sec_evidencias(ins: dict, styles: dict) -> list:
    """Histograma de scores + barras de critérios de desempate."""
    elems: list = []

    result_scores = _charts.chart_scores(ins.get("rank1_unico", pd.DataFrame()), ins.get("score_col", ""))
    img_scores    = embed_chart(result_scores)
    if img_scores:
        elems.append(img_scores)
        elems.append(Paragraph(
            "Score de identificação do candidato Rank 1 por composto. "
            "Verde ≥ 80 (alta confiança) · Azul 45–80 (moderada) · Vermelho < 45 (baixa). "
            "Linha pontilhada = limiar de alta confiança (80).",
            styles["Caption"],
        ))
        elems.append(spacer(0.4))

    criterio_counts = ins.get("criterio_counts", pd.Series(dtype="int64"))
    has_criterios   = hasattr(criterio_counts, "empty") and not criterio_counts.empty
    if has_criterios:
        result_crit = _charts.chart_criterios(criterio_counts)
        img_crit    = embed_chart(result_crit)
        if img_crit:
            elems.append(img_crit)
            elems.append(Paragraph(
                "Distribuição dos critérios que determinaram o Rank 1 para cada composto. "
                "Fragmentação MS/MS = critério de maior prioridade biológica (IST). "
                "Empate = compostos sem critério automático aplicável.",
                styles["Caption"],
            ))

    return elems


# ---------------------------------------------------------------------------
# Seção 9 — Nota metodológica
# ---------------------------------------------------------------------------

def _sec_metodologia(ins: dict, batch_info: Optional[dict], styles: dict) -> list:
    """Critérios IST, definição de scores, batch metadata, disclaimer."""
    elems: list = []

    elems.append(Paragraph(
        "Este relatório foi gerado pelo <b>Omics ETL Pipeline</b>, sistema de processamento "
        "e identificação de compostos desenvolvido para o IST Ambiental / SENAI. "
        "Os resultados são produto de análise automática baseada nos dados do equipamento "
        "LC-MS/MS e de bases de dados científicas públicas (PubChem, ChEBI).",
        styles["Metodologia"],
    ))
    elems.append(spacer(0.3))

    elems.append(Paragraph(
        "Ranking hierárquico IST — ordem de prioridade dos critérios:",
        styles["SubSection"],
    ))
    criterios = [
        ("1°", "Score de fragmentação MS/MS", "Correspondência com a biblioteca de fragmentos — maior poder biológico"),
        ("2°", "Score Lab",                   "Pontuação geral do software do instrumento"),
        ("3°", "Padrão isotópico",            "Similaridade com o padrão isotópico teórico"),
        ("4°", "Erro de massa (ppm)",          "Precisão de massa — menor erro é melhor"),
        ("5°", "Fórmula molecular",           "Desempate determinístico por ordem alfabética"),
        ("6°", "Empate humano",               "Sem critério automático — requer decisão do especialista"),
    ]
    crit_data = [
        [
            Paragraph(n,           styles["TableCell"]),
            Paragraph(f"<b>{c}</b>", styles["TableCell"]),
            Paragraph(d,           styles["TableCell"]),
        ]
        for n, c, d in criterios
    ]
    crit_tbl = Table(crit_data, colWidths=[0.8 * cm, 3.5 * cm, USABLE_W - 4.3 * cm])
    crit_tbl.setStyle(TableStyle([
        ("FONTSIZE",       (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [white, CINZA_TBL]),
        ("GRID",           (0, 0), (-1, -1), 0.25, HexColor("#d0d0d0")),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
        ("LEFTPADDING",    (0, 0), (-1, -1), 4),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(crit_tbl)
    elems.append(spacer(0.3))

    elems.append(Paragraph("Scores e métricas:", styles["SubSection"]))
    elems.append(Paragraph(
        "<b>Score Ranking (0–100):</b> média ponderada dos scores instrumentais "
        "(fragmentação 40% · lab 30% · isótopo 20% · massa 10%). "
        "Campo diagnóstico — não determina o Rank 1 no algoritmo atual.<br/>"
        "<b>Rank 1:</b> candidato mais compatível com o sinal segundo o algoritmo IST. "
        "Pode haver múltiplos Rank 1 em caso de empate — coluna Prioridade = Alta.",
        styles["Metodologia"],
    ))
    elems.append(spacer(0.3))

    if batch_info:
        elems.append(Paragraph("Dados do processamento:", styles["SubSection"]))
        data_ini = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
        data_fim = (batch_info.get("concluido_em") or "")[:16].replace("T", " ")
        elems.append(Paragraph(
            f"Arquivo de identificação: <b>{batch_info.get('nome_ident', '—')}</b><br/>"
            f"Arquivo de abundância: <b>{batch_info.get('nome_abund', '—')}</b><br/>"
            f"Processado em: {data_ini}  ·  Concluído em: {data_fim}",
            styles["Metodologia"],
        ))
        elems.append(spacer(0.3))

    elems.append(hr(color=HexColor("#aaaaaa"), thickness=0.3))
    elems.append(Paragraph(
        "<i>Os resultados apresentados neste relatório foram gerados automaticamente pelo pipeline "
        "Omics ETL e representam hipóteses de identificação baseadas em correspondência espectral "
        "e dados de bases científicas públicas. Nenhuma identificação aqui listada deve ser "
        "considerada definitiva sem validação pelo especialista analítico responsável. "
        "Compostos com Prioridade = Alta requerem obrigatoriamente revisão manual.</i>",
        styles["Disclaimer"],
    ))

    return elems


# ---------------------------------------------------------------------------
# Título
# ---------------------------------------------------------------------------

def _sec_titulo(ins: dict, batch_info: Optional[dict], styles: dict) -> list:
    elems = [Paragraph("Relatório Analítico de Identificação", styles["Title"])]

    if batch_info:
        data_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
        sub = (
            f"Análise #{batch_info['id']}  ·  {data_raw}  ·  "
            f"{batch_info.get('nome_ident', '—')}"
        )
    else:
        sub = "Análise mais recente com sucesso"

    elems.append(Paragraph(sub, styles["Subtitle"]))
    elems.append(hr())
    return elems


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def _build_story(
    ins: dict,
    nar: dict,
    batch_info: Optional[dict],
    cobertura_ext: dict,
    styles: dict,
) -> list:
    story: list = []

    # ── Página 1 — Diagnóstico ──────────────────────────────────────────────
    story += _sec_titulo(ins, batch_info, styles)
    story.append(spacer(0.3))

    story.append(Paragraph("Status da Análise", styles["SectionTitle"]))
    story += _sec_status(nar, styles)
    story.append(spacer(0.3))

    story += _sec_metricas_acao(nar, ins, styles)
    story.append(spacer(0.3))

    story.append(Paragraph("Diagnóstico Automático", styles["SectionTitle"]))
    story += _sec_diagnostico(nar, styles)
    story.append(spacer(0.3))

    story.append(Paragraph("Ações Recomendadas", styles["SectionTitle"]))
    story += _sec_acoes(ins, styles)

    # ── Página 2 — Compostos prioritários ──────────────────────────────────
    story.append(PageBreak())
    n_comp = ins.get("n_compostos", 0)
    story.append(Paragraph(
        f"Compostos Prioritários para Revisão  "
        f"<font size='9' color='#888888'>({n_comp} compostos)</font>",
        styles["SectionTitle"],
    ))
    story += _sec_compostos_prioritarios(nar, ins, styles)

    if ins.get("n_empates", 0) > 0 and ins.get("_tem_empate", False):
        story.append(spacer(0.4))
        story.append(Paragraph(
            f"Detalhe — Compostos em Empate  "
            f"<font size='9' color='#888888'>({ins['n_empates']} compostos)</font>",
            styles["SubSection"],
        ))
        story += _sec_empates_detalhe(ins, styles)

    # ── Página 3 — Perfil químico + Evidências técnicas ────────────────────
    story.append(PageBreak())

    perf_elems = _sec_perfil_quimico(ins, cobertura_ext, styles)
    if perf_elems:
        story.append(Paragraph("Perfil Químico da Análise", styles["SectionTitle"]))
        story += perf_elems
        story.append(spacer(0.4))

    story.append(Paragraph("Evidências Técnicas", styles["SectionTitle"]))
    story += _sec_evidencias(ins, styles)

    # ── Página 4 — Nota metodológica ────────────────────────────────────────
    story.append(PageBreak())
    story.append(Paragraph("Apêndice — Nota Metodológica", styles["SectionTitle"]))
    story += _sec_metodologia(ins, batch_info, styles)

    return story


# ---------------------------------------------------------------------------
# Ponto de entrada público — mesma assinatura de pdf_builder.gerar_relatorio_analitico
# ---------------------------------------------------------------------------

def gerar_relatorio_analitico(
    ins: dict,
    batch_info: Optional[dict] = None,
    cobertura_ext: Optional[dict] = None,
) -> bytes:
    """
    Gera o Relatório Analítico v2 em PDF e retorna os bytes.

    Args:
        ins:           Saída de src.reports.insights.computar_insights(df).
        batch_info:    Dict de metadata do batch; pode ser None.
        cobertura_ext: Saída de carregar_cobertura_externa(); pode ser None ou {}.

    Returns:
        Bytes do PDF gerado.

    Raises:
        ValueError: se ins estiver vazio.
    """
    if not ins:
        raise ValueError("Insights dict vazio — passe o resultado de computar_insights(df).")

    cobertura_ext = cobertura_ext or {}
    styles        = make_styles()
    nar           = gerar_narrativa(ins, cobertura_ext)

    if batch_info:
        d_raw   = (batch_info.get("iniciado_em") or "")[:10]
        b_label = (
            f"Análise #{batch_info['id']}  ·  {d_raw}  ·  "
            f"{batch_info.get('nome_ident', '')}"
        )
    else:
        b_label = "Análise mais recente"

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    hf_cb        = make_header_footer(b_label, generated_at, tipo_relatorio="Relatório Analítico")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title="Relatório Analítico de Identificação — Omics ETL",
        author="Omics ETL Pipeline · IST Ambiental / SENAI",
    )

    story = _build_story(ins, nar, batch_info, cobertura_ext, styles)
    doc.build(story, onFirstPage=hf_cb, onLaterPages=hf_cb)

    return buf.getvalue()
