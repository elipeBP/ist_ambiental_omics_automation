"""
Primitivas de layout ReportLab compartilhadas entre todos os builders de PDF.

Responsabilidades:
  - Constantes de página, margens e largura útil
  - Paleta de cores institucional IST
  - Estilos de parágrafo (ReportLab Platypus)
  - Header/footer parametrizável por tipo de relatório
  - Helpers genéricos: hr, spacer, embed_chart, trunc, plain, etc.
  - Badge de status colorido (RE + RA)
  - Subtabela de empates (RA + RT)

Regra de dependências:
  _shared.py → stdlib · reportlab · src.reports.insights
  NÃO importa: narrative · streamlit · charts (evita ciclos)
"""
from __future__ import annotations

import re
from io import BytesIO
from typing import Optional

import pandas as pd
from reportlab.lib.colors import HexColor, white
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from src.reports.insights import SCORE_TIER_ALTA, SCORE_TIER_MODERADA, strip_markdown

# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------

PAGE_W, PAGE_H = A4          # 595.28 × 841.89 pt
MARGIN_L = 2.0 * cm
MARGIN_R = 2.0 * cm
MARGIN_T = 2.6 * cm          # espaço extra para cabeçalho de página
MARGIN_B = 2.0 * cm
USABLE_W = PAGE_W - MARGIN_L - MARGIN_R   # ≈ 17.0 cm
CHART_W  = USABLE_W          # gráficos ocupam toda a largura útil

# ---------------------------------------------------------------------------
# Paleta de cores institucional IST
# ---------------------------------------------------------------------------

AZUL_IST      = HexColor("#2e5d8e")   # azul IST — títulos, cabeçalho
AZUL_MED      = HexColor("#4472c4")   # azul médio — destaques
VERDE_IST     = HexColor("#5a9e6f")   # verde — sucesso
AMARELO       = HexColor("#f5a623")   # amarelo — atenção
VERMELHO      = HexColor("#e57373")   # vermelho — alerta / empate
CINZA_CLARO   = HexColor("#f5f7fa")   # fundo de seções
CINZA_MED     = HexColor("#888888")   # texto secundário
CINZA_TBL     = HexColor("#f0f2f5")   # fundo alternado de tabela
AZUL_TBL      = HexColor("#dce8f5")   # fundo do cabeçalho de tabela
VERDE_CELL    = HexColor("#e8f5e9")   # célula score alta confiança
AMARELO_CELL  = HexColor("#fff8e1")   # célula score moderada
VERMELHO_CELL = HexColor("#ffebee")   # célula score baixa

# Mapeamento de cor de status para badge (fundo, texto)
_STATUS_BADGE_CORES: dict[str, tuple[HexColor, HexColor]] = {
    "verde":    (VERDE_IST,  HexColor("#1a3d24")),
    "amarelo":  (AMARELO,    HexColor("#5a3000")),
    "vermelho": (VERMELHO,   HexColor("#6b1c1c")),
}


# ---------------------------------------------------------------------------
# Estilos de parágrafo
# ---------------------------------------------------------------------------

def make_styles() -> dict:
    """Retorna dict com todos os estilos de parágrafo para os relatórios PDF."""
    base = getSampleStyleSheet()

    return {
        "Title": ParagraphStyle(
            "RPT_Title",
            parent=base["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=AZUL_IST,
            spaceAfter=2,
            leading=22,
        ),
        "Subtitle": ParagraphStyle(
            "RPT_Subtitle",
            parent=base["Normal"],
            fontSize=9.5,
            fontName="Helvetica",
            textColor=CINZA_MED,
            spaceAfter=4,
        ),
        "SectionTitle": ParagraphStyle(
            "RPT_Section",
            parent=base["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=AZUL_IST,
            spaceBefore=10,
            spaceAfter=5,
            leading=14,
        ),
        "SubSection": ParagraphStyle(
            "RPT_SubSection",
            parent=base["Normal"],
            fontSize=9.5,
            fontName="Helvetica-Bold",
            textColor=HexColor("#444444"),
            spaceBefore=6,
            spaceAfter=3,
        ),
        "Body": ParagraphStyle(
            "RPT_Body",
            parent=base["Normal"],
            fontSize=8.5,
            fontName="Helvetica",
            leading=12,
            textColor=HexColor("#222222"),
            spaceAfter=3,
        ),
        "Caption": ParagraphStyle(
            "RPT_Caption",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            textColor=CINZA_MED,
            leading=10,
            spaceAfter=4,
        ),
        "InsightSuccess": ParagraphStyle(
            "RPT_InsightSuccess",
            parent=base["Normal"],
            fontSize=8.5,
            fontName="Helvetica",
            leading=12,
            textColor=HexColor("#1b4f2a"),
            backColor=HexColor("#e8f5e9"),
            leftIndent=8,
            rightIndent=4,
            spaceAfter=3,
            spaceBefore=2,
            borderPadding=(5, 8, 5, 8),
        ),
        "InsightInfo": ParagraphStyle(
            "RPT_InsightInfo",
            parent=base["Normal"],
            fontSize=8.5,
            fontName="Helvetica",
            leading=12,
            textColor=HexColor("#1a3a5c"),
            backColor=HexColor("#e8f0f8"),
            leftIndent=8,
            rightIndent=4,
            spaceAfter=3,
            spaceBefore=2,
            borderPadding=(5, 8, 5, 8),
        ),
        "InsightWarning": ParagraphStyle(
            "RPT_InsightWarning",
            parent=base["Normal"],
            fontSize=8.5,
            fontName="Helvetica",
            leading=12,
            textColor=HexColor("#6d3800"),
            backColor=HexColor("#fff3e0"),
            leftIndent=8,
            rightIndent=4,
            spaceAfter=3,
            spaceBefore=2,
            borderPadding=(5, 8, 5, 8),
        ),
        "Metodologia": ParagraphStyle(
            "RPT_Metodologia",
            parent=base["Normal"],
            fontSize=8,
            fontName="Helvetica",
            textColor=HexColor("#444444"),
            leading=11,
            spaceAfter=3,
        ),
        "Disclaimer": ParagraphStyle(
            "RPT_Disclaimer",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica-Oblique",
            textColor=CINZA_MED,
            leading=10,
            spaceBefore=8,
            spaceAfter=3,
        ),
        "TableHeader": ParagraphStyle(
            "RPT_TableHeader",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica-Bold",
            textColor=white,
            leading=10,
            alignment=TA_CENTER,
        ),
        "TableCell": ParagraphStyle(
            "RPT_TableCell",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            textColor=HexColor("#222222"),
            leading=10,
        ),
        "MetricValue": ParagraphStyle(
            "RPT_MetricValue",
            parent=base["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=AZUL_IST,
            alignment=TA_CENTER,
            leading=22,
        ),
        "MetricLabel": ParagraphStyle(
            "RPT_MetricLabel",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            textColor=CINZA_MED,
            alignment=TA_CENTER,
            leading=10,
        ),
    }


# ---------------------------------------------------------------------------
# Header / Footer de página (canvas callback)
# ---------------------------------------------------------------------------

def make_header_footer(
    batch_label: str,
    generated_at: str,
    tipo_relatorio: str = "Relatório Analítico",
):
    """
    Retorna callable para onFirstPage / onLaterPages do SimpleDocTemplate.

    tipo_relatorio — exibido no canto direito do cabeçalho (ex.: "Relatório Executivo").
    """
    def _draw(canvas, doc):
        canvas.saveState()
        W, H = A4

        # Faixa de cabeçalho azul IST
        canvas.setFillColor(AZUL_IST)
        canvas.rect(MARGIN_L, H - 1.7 * cm, W - MARGIN_L - MARGIN_R, 0.75 * cm,
                    fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(
            MARGIN_L + 0.2 * cm, H - 1.28 * cm,
            "Omics ETL Pipeline  ·  IST Ambiental / SENAI",
        )
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(
            W - MARGIN_R - 0.1 * cm, H - 1.28 * cm,
            f"{tipo_relatorio}  ·  {batch_label}",
        )

        # Linha de rodapé
        canvas.setStrokeColor(HexColor("#cccccc"))
        canvas.setLineWidth(0.3)
        canvas.line(MARGIN_L, 1.75 * cm, W - MARGIN_R, 1.75 * cm)
        canvas.setFillColor(CINZA_MED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            MARGIN_L, 1.35 * cm,
            f"Gerado em {generated_at}  ·  Uso interno — sujeito a validação do especialista analítico",
        )
        canvas.drawRightString(W - MARGIN_R, 1.35 * cm, f"Página {doc.page}")
        canvas.restoreState()

    return _draw


# ---------------------------------------------------------------------------
# Helpers genéricos
# ---------------------------------------------------------------------------

def hr(color: HexColor = None, thickness: float = 0.5) -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=thickness,
        color=color if color is not None else AZUL_IST,
        spaceAfter=4,
        spaceBefore=4,
    )


def spacer(h_cm: float = 0.3) -> Spacer:
    return Spacer(1, h_cm * cm)


def embed_chart(
    result: Optional[tuple[bytes, float]],
    max_w: float = None,
) -> Optional[RLImage]:
    """Converte (bytes_png, aspect_ratio) em RLImage dimensionado para o PDF."""
    if result is None:
        return None
    data, aspect = result
    w = max_w if max_w is not None else CHART_W
    h = w * aspect
    return RLImage(BytesIO(data), width=w, height=h)


def trunc(s, n: int) -> str:
    """Trunca string com reticências se exceder n caracteres."""
    if not isinstance(s, str):
        s = str(s) if s is not None else "—"
    return (s[:n - 1] + "…") if len(s) > n else s


def plain(text: str) -> str:
    """Remove marcadores **bold** markdown para contextos sem renderização."""
    return strip_markdown(text).strip()


def score_cell_color(score) -> HexColor:
    """Retorna cor de fundo para célula de score (verde / amarelo / vermelho)."""
    try:
        v = float(score)
    except (TypeError, ValueError):
        return CINZA_TBL
    if v >= SCORE_TIER_ALTA:
        return VERDE_CELL
    if v >= SCORE_TIER_MODERADA:
        return AMARELO_CELL
    return VERMELHO_CELL


def insight_para(tipo: str, texto: str, styles: dict) -> Paragraph:
    """Parágrafo colorido por tipo de insight (success / warning / info)."""
    style_map = {
        "success": styles.get("InsightSuccess"),
        "warning": styles.get("InsightWarning"),
        "info":    styles.get("InsightInfo"),
    }
    style    = style_map.get(tipo) or styles["InsightInfo"]
    texto_rl = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    return Paragraph(texto_rl, style)


# ---------------------------------------------------------------------------
# Badge de status (RE + RA)
# ---------------------------------------------------------------------------

def status_badge_block(status_cor: str, label: str, styles: dict) -> Table:
    """
    Tabela 1×1 com fundo colorido simulando badge de status grande.

    status_cor — "verde" | "amarelo" | "vermelho"
    label      — texto exibido (ex.: "🟢  ANÁLISE CONCLUSIVA")
    """
    bg_color, text_color = _STATUS_BADGE_CORES.get(
        status_cor, (CINZA_MED, white)
    )

    badge_style = ParagraphStyle(
        "RPT_BadgeText",
        parent=styles.get("Body", getSampleStyleSheet()["Normal"]),
        fontSize=13,
        fontName="Helvetica-Bold",
        textColor=text_color,
        alignment=TA_CENTER,
        leading=18,
    )

    tbl = Table([[Paragraph(label, badge_style)]], colWidths=[USABLE_W])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), bg_color),
        ("TOPPADDING",    (0, 0), (0, 0), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING",   (0, 0), (0, 0), 12),
        ("RIGHTPADDING",  (0, 0), (0, 0), 12),
        ("ALIGN",         (0, 0), (0, 0), "CENTER"),
        ("VALIGN",        (0, 0), (0, 0), "MIDDLE"),
    ]))
    return tbl


# ---------------------------------------------------------------------------
# Subtabela de empates (RA + RT)
# ---------------------------------------------------------------------------

def build_empate_subtable(
    grupo: pd.DataFrame,
    score_col: str,
    styles: dict,
) -> Table:
    """Tabela compacta de candidatos empatados para um único composto."""
    _score_cols = [
        c for c in ["Score Fragmentacao", "Score Lab", "Isotope Similarity"]
        if c in grupo.columns
    ]
    disp_headers = {
        score_col:             "Score",
        "Score Fragmentacao":  "Fragmentação",
        "Score Lab":           "Score Lab",
        "Isotope Similarity":  "Isótopo",
    }

    row_header = [
        Paragraph(disp_headers.get(h, h), styles["TableHeader"])
        for h in ["Candidato", score_col] + _score_cols
    ]

    col_w_first = 5.5 * cm
    col_w_rest  = 1.8 * cm
    n_rest      = 1 + len(_score_cols)
    total_fixed = col_w_first + col_w_rest * n_rest
    if total_fixed < USABLE_W:
        col_w_first += USABLE_W - total_fixed
    col_widths = [col_w_first] + [col_w_rest] * n_rest

    _center = ParagraphStyle("RPT_EmpCenter", parent=styles["TableCell"], alignment=TA_CENTER)

    rows = [row_header]
    for _, r in grupo.iterrows():
        try:
            sc = f"{float(r.get(score_col, 0) or 0):.1f}"
        except (TypeError, ValueError):
            sc = "—"

        data_row = [
            Paragraph(trunc(str(r.get("Candidato") or "—"), 70), styles["TableCell"]),
            Paragraph(sc, _center),
        ]
        for col in _score_cols:
            try:
                v = f"{float(r.get(col, 0) or 0):.1f}"
            except (TypeError, ValueError):
                v = "—"
            data_row.append(Paragraph(v, _center))
        rows.append(data_row)

    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), HexColor("#5a6e8c")),
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
        ("ALIGN",          (1, 0), (-1, -1), "CENTER"),
    ]))
    return tbl
