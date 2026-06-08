"""
Relatório Executivo — Omics ETL Pipeline.

Audiência : gestores, coordenadores, reuniões de gestão.
Objetivo  : responder 5 perguntas de decisão em menos de 2 minutos.
Formato   : 1 página (análise conclusiva) ou 2 páginas (com revisões).

Perguntas respondidas:
  1. O experimento foi satisfatório?  → Status da análise
  2. Existem riscos?                  → Risco analítico
  3. Quantos compostos exigem revisão?→ Resultados em números
  4. Qual o perfil químico?           → Perfil da amostra
  5. Qual a recomendação?             → Bloco de recomendação

Regra: scores numéricos, critérios de desempate e jargão analítico
não aparecem neste relatório.

Dependências permitidas:
  pdf_executivo → _shared (layout) · narrative (interpretação)
  NÃO usa: charts · build_empate_subtable · insight_para · score_cell_color
"""
from __future__ import annotations

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

from src.reports._shared import (
    AMARELO_CELL,
    AZUL_IST,
    AZUL_TBL,
    CINZA_CLARO,
    CINZA_TBL,
    MARGIN_B,
    MARGIN_L,
    MARGIN_R,
    MARGIN_T,
    USABLE_W,
    VERDE_CELL,
    VERMELHO_CELL,
    hr,
    make_header_footer,
    make_styles,
    spacer,
    status_badge_block,
    trunc,
)
from src.reports.narrative import gerar_narrativa


# ---------------------------------------------------------------------------
# Constantes de cor por nível de risco
# ---------------------------------------------------------------------------

_RISCO_BG: dict[str, HexColor] = {
    "Baixo":    VERDE_CELL,
    "Moderado": AMARELO_CELL,
    "Elevado":  VERMELHO_CELL,
}

_RISCO_FG: dict[str, HexColor] = {
    "Baixo":    HexColor("#1b4f2a"),
    "Moderado": HexColor("#7a4000"),
    "Elevado":  HexColor("#8b0000"),
}

_RISCO_VALUE_COLOR: dict[str, HexColor] = {
    "Baixo":    HexColor("#1b5e20"),
    "Moderado": HexColor("#e65100"),
    "Elevado":  HexColor("#b71c1c"),
}

# Tradução de Situação para linguagem executiva
_SITUACAO_EXEC: dict[str, str] = {
    "Baixa confiança":    "Baixa correspondência",
    "Confiança moderada": "Correspondência parcial",
    "Alta confiança":     "Correspondência alta",
}


# ---------------------------------------------------------------------------
# Helper: faixa de seção (visual diferenciado do RA)
# ---------------------------------------------------------------------------

def _band(title: str, styles: dict) -> Table:
    """
    Cabeçalho de seção em faixa cinza.
    Visual de apresentação executiva — diferente do SectionTitle azul do RA.
    """
    _s = ParagraphStyle(
        "BandTitle",
        parent=styles.get("SubSection", styles["Body"]),
        spaceBefore=0,
        spaceAfter=0,
        fontSize=9.5,
        fontName="Helvetica-Bold",
        textColor=HexColor("#3d3d3d"),
    )
    tbl = Table([[Paragraph(title, _s)]], colWidths=[USABLE_W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), CINZA_CLARO),
        ("LEFTPADDING",   (0, 0), (0, 0), 10),
        ("RIGHTPADDING",  (0, 0), (0, 0), 8),
        ("TOPPADDING",    (0, 0), (0, 0), 5),
        ("BOTTOMPADDING", (0, 0), (0, 0), 5),
        ("BOX",           (0, 0), (0, 0), 0.3, HexColor("#c8c8c8")),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Helper: bloco de risco colorido
# ---------------------------------------------------------------------------

def _risco_block(risco_label: str, risco_desc: str, styles: dict) -> Table:
    """Bloco 1×1 com fundo colorido por nível de risco."""
    bg   = _RISCO_BG.get(risco_label, CINZA_CLARO)
    fg   = _RISCO_FG.get(risco_label, HexColor("#444444"))
    _s   = ParagraphStyle(
        "RiscoBody",
        parent=styles["Body"],
        textColor=fg,
        fontSize=9,
        leading=13,
    )
    text = f"<b>{risco_label.upper()}</b> — {risco_desc}"
    tbl  = Table([[Paragraph(text, _s)]], colWidths=[USABLE_W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), bg),
        ("LEFTPADDING",   (0, 0), (0, 0), 12),
        ("RIGHTPADDING",  (0, 0), (0, 0), 12),
        ("TOPPADDING",    (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 10),
        ("BOX",           (0, 0), (0, 0), 0.5, fg),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Helper: bloco de recomendação com barra lateral azul IST
# ---------------------------------------------------------------------------

def _recomendacao_block(recomendacao: str, styles: dict) -> Table:
    """
    Bloco visual dominante da página executiva.
    Barra esquerda AZUL_IST + fundo AZUL_TBL claro + texto em destaque.
    """
    _s = ParagraphStyle(
        "RecText",
        parent=styles["Body"],
        textColor=HexColor("#1a2a3a"),
        fontSize=9,
        leading=14,
    )
    text = f"<b>RECOMENDAÇÃO</b>  —  {recomendacao}"

    # Col 1: barra azul sólida (8pt) | Col 2: conteúdo
    tbl = Table(
        [[Paragraph("", styles["Body"]), Paragraph(text, _s)]],
        colWidths=[8, USABLE_W - 8],
    )
    tbl.setStyle(TableStyle([
        # Barra azul esquerda
        ("BACKGROUND",    (0, 0), (0, 0), AZUL_IST),
        ("LEFTPADDING",   (0, 0), (0, 0), 0),
        ("RIGHTPADDING",  (0, 0), (0, 0), 0),
        ("TOPPADDING",    (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        # Conteúdo
        ("BACKGROUND",    (1, 0), (1, 0), AZUL_TBL),
        ("LEFTPADDING",   (1, 0), (1, 0), 14),
        ("RIGHTPADDING",  (1, 0), (1, 0), 12),
        ("TOPPADDING",    (1, 0), (1, 0), 12),
        ("BOTTOMPADDING", (1, 0), (1, 0), 12),
        ("VALIGN",        (0, 0), (-1, 0), "MIDDLE"),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Tradução de Situação para linguagem executiva
# ---------------------------------------------------------------------------

def _situacao_exec(s: str) -> str:
    """Converte Situação técnica para linguagem de gestores."""
    if "Empate" in s or "empate" in s:
        return "Identidade incerta"
    return _SITUACAO_EXEC.get(s, s)


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------

def _sec_titulo_exec(batch_info: Optional[dict], styles: dict) -> list:
    elems = [Paragraph("Relatório Executivo de Identificação", styles["Title"])]

    if batch_info:
        data_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
        sub = f"Análise #{batch_info['id']}  ·  {data_raw}  ·  {batch_info.get('nome_ident', '—')}"
    else:
        sub = "Análise mais recente com sucesso"

    elems.append(Paragraph(sub, styles["Subtitle"]))
    elems.append(hr())
    return elems


def _sec_status_exec(nar: dict, styles: dict) -> list:
    """Badge de status + resumo executivo em linguagem não técnica."""
    badge = status_badge_block(nar["status_cor"], nar["status_label"].upper(), styles)
    para  = Paragraph(nar["paragrafo_exec"], styles["Body"])
    return [KeepTogether([badge, spacer(0.2), para])]


def _sec_numeros(nar: dict, ins: dict, styles: dict) -> list:
    """4 cards: compostos identificados / para revisão / identidade incerta / risco."""
    n_comp  = ins.get("n_compostos", 0)
    n_rev   = nar["n_revisar"]
    n_crit  = nar["n_criticos"]
    risco   = nar["risco_label"]

    pct_rev  = f" ({n_rev / n_comp * 100:.0f}%)" if n_comp else ""
    risco_fg = _RISCO_VALUE_COLOR.get(risco, AZUL_IST)

    _risco_val = ParagraphStyle(
        "RiscoVal",
        parent=styles["MetricValue"],
        textColor=risco_fg,
        fontSize=15,   # ligeiramente menor — palavra em vez de número
    )

    data = [
        [
            Paragraph(str(n_comp),           styles["MetricValue"]),
            Paragraph(f"{n_rev}{pct_rev}",   styles["MetricValue"]),
            Paragraph(str(n_crit),           styles["MetricValue"]),
            Paragraph(risco,                 _risco_val),
        ],
        [
            Paragraph("Compostos<br/>identificados", styles["MetricLabel"]),
            Paragraph("Para<br/>revisão",            styles["MetricLabel"]),
            Paragraph("Identidade<br/>incerta",       styles["MetricLabel"]),
            Paragraph("Risco<br/>analítico",          styles["MetricLabel"]),
        ],
    ]

    col_w = USABLE_W / 4
    tbl   = Table(data, colWidths=[col_w] * 4)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), CINZA_CLARO),
        ("BACKGROUND",    (0, 1), (-1, 1), white),
        ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#d0d8e0")),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, HexColor("#dce3ea")),
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [tbl]


def _sec_perfil_exec(nar: dict, ins: dict, styles: dict) -> list:
    """Top-3 classes químicas em tabela simples — sem scores, sem jargão."""
    classes_df = ins.get("classes_classif", pd.DataFrame())

    if classes_df.empty:
        # Fallback: entrada "Perfil" em nar["dimensoes"]
        perfil = next(
            (d for d in nar.get("dimensoes", []) if "Perfil" in d[0]),
            None,
        )
        if not perfil:
            return []
        return [Paragraph(f"Perfil predominante: <b>{perfil[1]}</b>", styles["Body"])]

    n_comp  = ins.get("n_compostos", 1) or 1
    top3    = classes_df.head(3)

    # Detecta coluna de nome da classe (robustez)
    cls_col = next(
        (c for c in ["Categoria", "Classe química", "Classe Quimica"] if c in top3.columns),
        top3.columns[0],
    )

    _head = ParagraphStyle(
        "PerfHead", parent=styles["TableHeader"], fontSize=8,
    )
    _cell = ParagraphStyle(
        "PerfCell", parent=styles["TableCell"], fontSize=8.5,
    )
    _num  = ParagraphStyle(
        "PerfNum", parent=styles["TableCell"], fontSize=8.5, alignment=TA_CENTER,
    )

    col_w1 = USABLE_W * 0.55
    col_w2 = USABLE_W - col_w1

    rows = [[Paragraph("Grupo de compostos", _head), Paragraph("Frequência", _head)]]
    for _, row in top3.iterrows():
        cls_name = str(row.get(cls_col, "—"))
        freq     = int(row.get("Frequência", 0))
        pct      = freq / n_comp * 100
        rows.append([
            Paragraph(trunc(cls_name, 45), _cell),
            Paragraph(f"{freq} de {n_comp}  ({pct:.0f}%)", _num),
        ])

    tbl = Table(rows, colWidths=[col_w1, col_w2])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), AZUL_IST),
        ("TEXTCOLOR",      (0, 0), (-1, 0), white),
        ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, CINZA_TBL]),
        ("GRID",           (0, 0), (-1, -1), 0.25, HexColor("#d0d0d0")),
        ("TOPPADDING",     (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ("LEFTPADDING",    (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 8),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [KeepTogether([tbl])]


def _sec_risco_exec(nar: dict, styles: dict) -> list:
    """Bloco colorido de risco analítico — responde Q2."""
    return [_risco_block(nar["risco_label"], nar["risco_desc"], styles)]


def _sec_recomendacao(nar: dict, styles: dict) -> list:
    """Bloco de recomendação com barra azul — elemento visual dominante da p.1."""
    return [KeepTogether([_recomendacao_block(nar["recomendacao"], styles)])]


def _sec_compostos_revisao(nar: dict, styles: dict) -> list:
    """
    Tabela simplificada: apenas compostos Alta + Média prioridade.
    3 colunas (sem scores), máximo 15 linhas + nota de overflow.
    """
    priority_df = nar.get("priority_df", pd.DataFrame())
    if priority_df.empty:
        return []

    df_rev = priority_df[
        priority_df["Prioridade"].isin(["🔴 Alta", "🟡 Média"])
    ].copy()

    if df_rev.empty:
        return []

    overflow = max(0, len(df_rev) - 15)
    if overflow:
        df_rev = df_rev.head(15)

    _cell = ParagraphStyle("RevCell", parent=styles["TableCell"], fontSize=8.5, leading=11)
    _head = styles["TableHeader"]

    col_sinal   = USABLE_W * 0.22
    col_sit     = USABLE_W * 0.30
    col_cand    = USABLE_W - col_sinal - col_sit

    rows = [[
        Paragraph("Composto",              _head),
        Paragraph("Situação",              _head),
        Paragraph("Candidato mais provável", _head),
    ]]

    row_bgs: list[HexColor] = []
    for _, row in df_rev.iterrows():
        prio  = str(row.get("Prioridade", ""))
        sinal = trunc(str(row.get("Composto", "—")), 22)
        sit   = _situacao_exec(str(row.get("Situação", "—")))
        cand  = trunc(str(row.get("Candidato mais provável", "—")), 48)

        rows.append([
            Paragraph(sinal, _cell),
            Paragraph(sit,   _cell),
            Paragraph(cand,  _cell),
        ])
        row_bgs.append(VERMELHO_CELL if "Alta" in prio else AMARELO_CELL)

    tbl = Table(rows, colWidths=[col_sinal, col_sit, col_cand], repeatRows=1)
    ts  = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), AZUL_IST),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("GRID",          (0, 0), (-1, -1), 0.25, HexColor("#cccccc")),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ])
    for i, bg in enumerate(row_bgs, start=1):
        ts.add("BACKGROUND", (0, i), (-1, i), bg)
    tbl.setStyle(ts)

    elems: list = [tbl]

    if overflow:
        elems.append(spacer(0.15))
        elems.append(Paragraph(
            f"<i>E mais {overflow} compostos — consultar o Relatório Analítico para a lista completa.</i>",
            styles["Caption"],
        ))

    return elems


# ---------------------------------------------------------------------------
# Orquestrador
# ---------------------------------------------------------------------------

def _build_story(
    ins: dict,
    nar: dict,
    batch_info: Optional[dict],
    styles: dict,
) -> list:
    story: list = []

    # ── Página 1 — Diagnóstico executivo ────────────────────────────────────
    story += _sec_titulo_exec(batch_info, styles)
    story.append(spacer(0.25))

    story += _sec_status_exec(nar, styles)
    story.append(spacer(0.35))

    story.append(_band("Resultados em Números", styles))
    story.append(spacer(0.15))
    story += _sec_numeros(nar, ins, styles)
    story.append(spacer(0.35))

    perf_elems = _sec_perfil_exec(nar, ins, styles)
    if perf_elems:
        story.append(_band("Perfil Químico da Amostra", styles))
        story.append(spacer(0.15))
        story += perf_elems
        story.append(spacer(0.35))

    story.append(_band("Risco Analítico", styles))
    story.append(spacer(0.15))
    story += _sec_risco_exec(nar, styles)
    story.append(spacer(0.35))

    story.append(_band("Recomendação", styles))
    story.append(spacer(0.15))
    story += _sec_recomendacao(nar, styles)

    # ── Página 2 — Compostos para revisão (condicional) ─────────────────────
    if nar["n_revisar"] > 0:
        story.append(PageBreak())
        story.append(_band(
            f"Compostos que Exigem Revisão  ({nar['n_revisar']} compostos)",
            styles,
        ))
        story.append(spacer(0.2))
        story += _sec_compostos_revisao(nar, styles)

    # ── Nota final ────────────────────────────────────────────────────────────
    story.append(spacer(0.4))
    story.append(hr(color=HexColor("#cccccc"), thickness=0.3))
    story.append(Paragraph(
        "<i>Gerado automaticamente pelo Omics ETL Pipeline  ·  "
        "Resultados sujeitos à validação pelo especialista analítico antes de uso definitivo.</i>",
        styles["Disclaimer"],
    ))

    return story


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def gerar_relatorio_executivo(
    ins: dict,
    batch_info: Optional[dict] = None,
    cobertura_ext: Optional[dict] = None,
) -> bytes:
    """
    Gera o Relatório Executivo em PDF e retorna os bytes.

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
        b_label = f"Análise #{batch_info['id']}  ·  {d_raw}"
    else:
        b_label = "Análise mais recente"

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    hf_cb        = make_header_footer(b_label, generated_at, tipo_relatorio="Relatório Executivo")

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
        title="Relatório Executivo — Omics ETL",
        author="Omics ETL Pipeline · IST Ambiental / SENAI",
    )

    story = _build_story(ins, nar, batch_info, styles)
    doc.build(story, onFirstPage=hf_cb, onLaterPages=hf_cb)

    return buf.getvalue()
