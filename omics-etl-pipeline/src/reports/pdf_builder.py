"""
Montagem do Relatório Analítico em PDF.

Tecnologia: ReportLab (Platypus API) + matplotlib (gráficos via charts.py).
Geração 100% em memória — retorna bytes, sem arquivos temporários em disco.

Uso:
    from src.reports.pdf_builder import gerar_relatorio_analitico

    pdf_bytes = gerar_relatorio_analitico(ins, batch_info, cobertura_ext)
    # ins         — saída de src.reports.insights.computar_insights(df)
    # batch_info  — dict de src.database.batch.listar_batches()
    # cobertura_ext — dict de src.ui.utils.carregar_cobertura_externa()
"""
from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO
from typing import Optional

import pandas as pd

from reportlab.lib import colors
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from src.reports import charts as _charts
from src.reports.insights import CRITERIO_LABEL, strip_markdown

# ---------------------------------------------------------------------------
# Constantes de layout
# ---------------------------------------------------------------------------
_PAGE_W, _PAGE_H = A4          # 595.28 × 841.89 pt
_MARGIN_L = 2.0 * cm
_MARGIN_R = 2.0 * cm
_MARGIN_T = 2.6 * cm           # espaço extra para cabeçalho de página
_MARGIN_B = 2.0 * cm
_USABLE_W = _PAGE_W - _MARGIN_L - _MARGIN_R   # ≈ 17.0 cm

_CHART_W  = _USABLE_W          # gráficos ocupam toda a largura útil

# Cores institucionais
_AZUL_IST   = HexColor("#2e5d8e")   # azul IST — títulos, cabeçalho
_AZUL_MED   = HexColor("#4472c4")   # azul médio — destaques
_VERDE_IST  = HexColor("#5a9e6f")   # verde — sucesso
_AMARELO    = HexColor("#f5a623")   # amarelo — atenção
_VERMELHO   = HexColor("#e57373")   # vermelho — empate / alerta
_CINZA_CLARO = HexColor("#f5f7fa")  # fundo de seções
_CINZA_MED  = HexColor("#888888")
_CINZA_TBL  = HexColor("#f0f2f5")   # fundo alternado da tabela
_AZUL_TBL   = HexColor("#dce8f5")   # fundo do cabeçalho da tabela
_VERDE_CELL = HexColor("#e8f5e9")   # célula de score alta confiança
_AMARELO_CELL = HexColor("#fff8e1") # célula score moderada
_VERMELHO_CELL = HexColor("#ffebee")# célula score baixa


# ---------------------------------------------------------------------------
# Estilos de parágrafo
# ---------------------------------------------------------------------------

def _make_styles() -> dict:
    base = getSampleStyleSheet()

    return {
        "Title": ParagraphStyle(
            "RPT_Title",
            parent=base["Normal"],
            fontSize=18,
            fontName="Helvetica-Bold",
            textColor=_AZUL_IST,
            spaceAfter=2,
            leading=22,
        ),
        "Subtitle": ParagraphStyle(
            "RPT_Subtitle",
            parent=base["Normal"],
            fontSize=9.5,
            fontName="Helvetica",
            textColor=_CINZA_MED,
            spaceAfter=4,
        ),
        "SectionTitle": ParagraphStyle(
            "RPT_Section",
            parent=base["Normal"],
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=_AZUL_IST,
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
            textColor=_CINZA_MED,
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
            textColor=_CINZA_MED,
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
            textColor=_AZUL_IST,
            alignment=TA_CENTER,
            leading=22,
        ),
        "MetricLabel": ParagraphStyle(
            "RPT_MetricLabel",
            parent=base["Normal"],
            fontSize=7.5,
            fontName="Helvetica",
            textColor=_CINZA_MED,
            alignment=TA_CENTER,
            leading=10,
        ),
    }


# ---------------------------------------------------------------------------
# Header / Footer de página (canvas callbacks)
# ---------------------------------------------------------------------------

def _make_header_footer(batch_label: str, generated_at: str):
    """Retorna callable para onFirstPage / onLaterPages do SimpleDocTemplate."""
    def _draw(canvas, doc):
        canvas.saveState()
        W, H = A4

        # — Faixa de cabeçalho —
        canvas.setFillColor(_AZUL_IST)
        canvas.rect(_MARGIN_L, H - 1.7 * cm, W - _MARGIN_L - _MARGIN_R, 0.75 * cm,
                    fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(_MARGIN_L + 0.2 * cm, H - 1.28 * cm,
                          "Omics ETL Pipeline  ·  IST Ambiental / SENAI")
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(W - _MARGIN_R - 0.1 * cm, H - 1.28 * cm, batch_label)

        # — Linha de rodapé —
        canvas.setStrokeColor(HexColor("#cccccc"))
        canvas.setLineWidth(0.3)
        canvas.line(_MARGIN_L, 1.75 * cm, W - _MARGIN_R, 1.75 * cm)

        canvas.setFillColor(_CINZA_MED)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(
            _MARGIN_L,
            1.35 * cm,
            f"Gerado em {generated_at}  ·  Uso interno — sujeito a validação do especialista analítico",
        )
        canvas.drawRightString(
            W - _MARGIN_R,
            1.35 * cm,
            f"Página {doc.page}",
        )
        canvas.restoreState()

    return _draw


# ---------------------------------------------------------------------------
# Helpers de construção de conteúdo
# ---------------------------------------------------------------------------

def _hr(color=_AZUL_IST, thickness=0.5) -> HRFlowable:
    return HRFlowable(
        width="100%",
        thickness=thickness,
        color=color,
        spaceAfter=4,
        spaceBefore=4,
    )


def _spacer(h_cm: float = 0.3) -> Spacer:
    return Spacer(1, h_cm * cm)


def _embed_chart(result: Optional[tuple[bytes, float]], max_w: float = _CHART_W) -> Optional[RLImage]:
    """Converte (bytes, aspect_ratio) em RLImage dimensionado para o PDF."""
    if result is None:
        return None
    data, aspect = result
    h = max_w * aspect
    return RLImage(BytesIO(data), width=max_w, height=h)


def _score_cell_color(score) -> HexColor:
    """Retorna cor de fundo para célula de score."""
    try:
        v = float(score)
    except (TypeError, ValueError):
        return _CINZA_TBL
    if v >= 80:
        return _VERDE_CELL
    if v >= 45:
        return _AMARELO_CELL
    return _VERMELHO_CELL


def _trunc(s, n: int) -> str:
    if not isinstance(s, str):
        s = str(s) if s is not None else "—"
    return (s[:n - 1] + "…") if len(s) > n else s


def _plain(text: str) -> str:
    """Remove markdown **bold** e limpa texto para o PDF."""
    return strip_markdown(text).strip()


def _insight_para(tipo: str, texto: str, styles: dict) -> Paragraph:
    """Parágrafo de insight com backColor por tipo."""
    style_map = {
        "success": styles["InsightSuccess"],
        "warning": styles["InsightWarning"],
        "info":    styles["InsightInfo"],
    }
    style = style_map.get(tipo, styles["InsightInfo"])
    # Marca **bold** → <b>bold</b> para ReportLab
    texto_rl = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto)
    return Paragraph(texto_rl, style)


# ---------------------------------------------------------------------------
# Seções do relatório
# ---------------------------------------------------------------------------

def _sec_titulo(ins: dict, batch_info: Optional[dict], styles: dict) -> list:
    elems = []

    # Título principal
    elems.append(Paragraph("Relatório Analítico de Identificação", styles["Title"]))

    # Subtítulo com info do batch
    if batch_info:
        data_raw = (batch_info.get("iniciado_em") or "")[:16].replace("T", " ")
        sub = (
            f"Análise #{batch_info['id']}  ·  {data_raw}  ·  "
            f"{batch_info.get('nome_ident', '—')}"
        )
    else:
        sub = "Análise mais recente com sucesso"
    elems.append(Paragraph(sub, styles["Subtitle"]))
    elems.append(_hr())
    return elems


def _sec_resumo(ins: dict, cobertura_ext: dict, styles: dict) -> list:
    """Tabela de métricas: 5 células em 1 linha."""
    n_comp    = ins["n_compostos"]
    n_cand    = ins["n_candidatos_tot"]
    score_med = ins["mean_pontuacao"]
    n_emp     = ins["n_empates"]
    pct_emp   = ins["pct_empates"]
    cand_comp = ins["mean_cand_comp"]
    n_resol   = ins["n_resolvidos"]
    n_nresol  = ins["n_nao_resolvidos"]

    def _card(valor, label):
        return [
            Paragraph(str(valor), styles["MetricValue"]),
            Paragraph(label,      styles["MetricLabel"]),
        ]

    # Linha de valores e labels numa tabela 2×5
    emp_str  = (f"{n_emp} ({pct_emp:.0f}%)" if ins["_tem_empate"] else "—")
    resol_str = f"{n_resol}/{n_comp}" if n_resol else "—"

    data = [
        # linha de valores
        [
            Paragraph(str(n_comp),         styles["MetricValue"]),
            Paragraph(f"{score_med:.1f}",  styles["MetricValue"]),
            Paragraph(emp_str,             styles["MetricValue"]),
            Paragraph(f"{cand_comp:.1f}",  styles["MetricValue"]),
            Paragraph(resol_str,           styles["MetricValue"]),
        ],
        # linha de labels
        [
            Paragraph("Compostos<br/>detectados",       styles["MetricLabel"]),
            Paragraph("Score médio<br/>Rank 1 (0–100)", styles["MetricLabel"]),
            Paragraph("Em empate<br/>(Rank 1)",          styles["MetricLabel"]),
            Paragraph("Candidatos<br/>por composto",     styles["MetricLabel"]),
            Paragraph("Resolvidos<br/>automaticamente",  styles["MetricLabel"]),
        ],
    ]

    col_w = _USABLE_W / 5
    tbl = Table(data, colWidths=[col_w] * 5)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _CINZA_CLARO),
        ("BACKGROUND",    (0, 1), (-1, 1), HexColor("#ffffff")),
        ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#d0d8e0")),
        ("INNERGRID",     (0, 0), (-1, -1), 0.3, HexColor("#dce3ea")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elems = [tbl]

    # Cobertura externa (ChEBI / PubChem) como linha adicional se disponível
    if cobertura_ext:
        pct_chebi   = cobertura_ext.get("pct_chebi", 0)
        pct_pubchem = cobertura_ext.get("pct_pubchem", 0)
        elems.append(_spacer(0.2))
        elems.append(Paragraph(
            f"Cobertura de bases externas (Rank 1): "
            f"<b>ChEBI {pct_chebi:.0f}%</b>  ·  "
            f"<b>PubChem {pct_pubchem:.0f}%</b>",
            styles["Caption"],
        ))

    return elems


def _sec_insights(ins: dict, styles: dict) -> list:
    elems: list = []
    for tipo, texto in ins["insights"]:
        elems.append(_insight_para(tipo, texto, styles))
    return elems


def _sec_chart_criterios(ins: dict, styles: dict) -> list:
    elems: list = []
    result = _charts.chart_criterios(ins["criterio_counts"])
    img    = _embed_chart(result)
    if img:
        elems.append(img)
        elems.append(Paragraph(
            "Distribuição dos critérios que determinaram o Rank 1 para cada composto. "
            "Fragmentação MS/MS = critério de maior prioridade biológica (IST). "
            "Barras vermelhas indicam compostos que requerem decisão humana.",
            styles["Caption"],
        ))
    return elems


def _sec_chart_scores(ins: dict, styles: dict) -> list:
    elems: list = []
    result = _charts.chart_scores(ins["rank1_unico"], ins["score_col"])
    img    = _embed_chart(result)
    if img:
        elems.append(img)
        elems.append(Paragraph(
            "Score de identificação do candidato mais provável (Rank 1) para cada composto. "
            "Verde ≥ 80 (alta confiança) · Azul 45–80 (moderada) · Vermelho < 45 (baixa). "
            "Linha pontilhada vermelha = limiar de alta confiança (80).",
            styles["Caption"],
        ))
    return elems


def _sec_chart_classes(ins: dict, cobertura_ext: dict, styles: dict) -> list:
    elems: list = []
    if ins["classes_classif"].empty:
        return elems

    result = _charts.chart_classes(ins["classes_classif"])
    img    = _embed_chart(result)
    if img:
        elems.append(img)

        n_classif = ins["n_classif"]
        n_nc      = ins["n_nc"]
        n_comp    = ins["n_compostos"]
        cap_parts = [
            f"Classes químicas dos candidatos Rank 1 (ChEBI). "
            f"{n_classif} de {n_comp} compostos classificados. "
            f"{n_nc} sem classificação documentada.",
        ]
        elems.append(Paragraph(" ".join(cap_parts), styles["Caption"]))

    return elems


def _sec_tabela_rank1(ins: dict, styles: dict) -> list:
    """Tabela completa de Rank 1 por composto — ordenada por score ascendente."""
    rank1_unico  = ins["rank1_unico"]
    compound_data = ins["compound_data"]
    score_col     = ins["score_col"]
    _tem_criterio = ins["_tem_criterio"]
    _tem_classes  = ins["_tem_classes"]
    _tem_empate   = ins["_tem_empate"]

    # Enriquece compound_data com colunas extras do rank1_unico
    _extra_cols = ["Sinal"]
    for col in ["Formula", "Classe Quimica", "Criterio Desempate", "Empate"]:
        if col in rank1_unico.columns:
            _extra_cols.append(col)
    rank1_extra = rank1_unico[_extra_cols].reset_index(drop=True)
    tbl_df = compound_data.merge(rank1_extra, on="Sinal", how="left")
    # Piores primeiro (requerem atenção prioritária)
    tbl_df = tbl_df.sort_values("pontuacao_rank1", ascending=True, na_position="last")

    # -- Definição das colunas --
    # Fixas sempre presentes
    headers = ["Composto", "Candidato Rank 1", "Score"]
    col_ws  = [2.8 * cm, 5.5 * cm, 1.5 * cm]

    if _tem_classes and "Classe Quimica" in tbl_df.columns:
        headers.insert(2, "Classe")
        col_ws.insert(2, 2.8 * cm)

    if "Formula" in tbl_df.columns:
        headers.insert(2, "Fórmula")
        col_ws.insert(2, 1.9 * cm)

    if _tem_criterio and "Criterio Desempate" in tbl_df.columns:
        headers.append("Critério")
        col_ws.append(2.5 * cm)

    if _tem_empate and "Empate" in tbl_df.columns:
        headers.append("Emp.")
        col_ws.append(1.2 * cm)

    # Ajusta larguras para somar _USABLE_W
    soma = sum(col_ws)
    if soma < _USABLE_W:
        # distribui sobra para "Candidato"
        idx_cand = 1  # sempre índice 1 após "Composto"
        col_ws[idx_cand] += _USABLE_W - soma

    # -- Construção das linhas --
    header_row = [Paragraph(h, styles["TableHeader"]) for h in headers]
    rows = [header_row]

    score_col_idx = headers.index("Score")
    emp_col_idx   = headers.index("Emp.") if "Emp." in headers else None

    row_scores = []
    row_empates = []

    for _, row in tbl_df.iterrows():
        score_val = row.get("pontuacao_rank1")
        is_tied   = bool(pd.to_numeric(row.get("Empate", 0), errors="coerce") or 0)

        try:
            score_str = f"{float(score_val):.1f}" if pd.notna(score_val) else "—"
        except (TypeError, ValueError):
            score_str = "—"

        # Critério: label legível
        crit_raw = row.get("Criterio Desempate", "—") or "—"
        crit_lbl = CRITERIO_LABEL.get(str(crit_raw), str(crit_raw))
        if crit_lbl == "Empate — decisão humana":
            crit_lbl = "Empate"

        data_row = [
            Paragraph(_trunc(str(row.get("Sinal") or "—"), 22),    styles["TableCell"]),
            Paragraph(_trunc(str(row.get("melhor_candidato") or "—"), 60), styles["TableCell"]),
        ]

        if "Fórmula" in headers:
            data_row.append(Paragraph(_trunc(str(row.get("Formula") or "—"), 15), styles["TableCell"]))
        if "Classe" in headers:
            data_row.append(Paragraph(_trunc(str(row.get("Classe Quimica") or "—"), 30), styles["TableCell"]))

        data_row.append(Paragraph(score_str, ParagraphStyle(
            "ScoreCell",
            parent=styles["TableCell"],
            alignment=TA_CENTER,
            fontName="Helvetica-Bold",
        )))

        if "Critério" in headers:
            data_row.append(Paragraph(_trunc(crit_lbl, 22), styles["TableCell"]))
        if emp_col_idx is not None:
            emp_sym = "✓" if is_tied else "—"
            data_row.append(Paragraph(emp_sym, ParagraphStyle(
                "EmpCell",
                parent=styles["TableCell"],
                alignment=TA_CENTER,
                textColor=HexColor("#c0392b") if is_tied else HexColor("#888888"),
                fontName="Helvetica-Bold" if is_tied else "Helvetica",
            )))

        rows.append(data_row)
        row_scores.append(score_val)
        row_empates.append(is_tied)

    tbl = Table(rows, colWidths=col_ws, repeatRows=1)

    ts = TableStyle([
        # Cabeçalho
        ("BACKGROUND",    (0, 0), (-1, 0), _AZUL_IST),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 7.5),
        ("ALIGN",         (0, 0), (-1, 0), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        # Dados
        ("FONTSIZE",      (0, 1), (-1, -1), 7.5),
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.25, HexColor("#cccccc")),
        # Linhas alternadas
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, _CINZA_TBL]),
    ])

    # Cor da célula de score por tier
    for i, (score_val, is_tied) in enumerate(zip(row_scores, row_empates), start=1):
        ts.add("BACKGROUND", (score_col_idx, i), (score_col_idx, i),
               _score_cell_color(score_val))
        if is_tied and emp_col_idx is not None:
            ts.add("BACKGROUND", (emp_col_idx, i), (emp_col_idx, i),
                   HexColor("#fff0f0"))

    tbl.setStyle(ts)

    n = len(tbl_df)
    cap = (
        f"Tabela com os {n} compostos do experimento, ordenada por score ascendente "
        "(compostos com maior incerteza aparecem primeiro — revisão prioritária). "
        "✓ na coluna Emp. indica candidatos em empate no Rank 1, que requerem "
        "decisão do especialista."
    )
    return [tbl, _spacer(0.2), Paragraph(cap, styles["Caption"])]


def _sec_empates(ins: dict, styles: dict) -> list:
    """Tabela detalhada dos compostos em empate e seus candidatos."""
    if ins["n_empates"] == 0 or not ins["_tem_empate"]:
        return []

    rank1_df  = ins["rank1_df"]
    rank1_unico = ins["rank1_unico"]
    score_col = ins["score_col"]

    _emp_num  = pd.to_numeric(rank1_unico["Empate"], errors="coerce").fillna(0)
    emp_sinais = rank1_unico[_emp_num > 0]["Sinal"].tolist()

    elems: list = [
        Paragraph(
            f"Os {len(emp_sinais)} compostos abaixo possuem dois ou mais candidatos com "
            "identificação automaticamente indistinguível (mesmos scores em todos os critérios). "
            "A decisão do candidato definitivo requer avaliação pelo especialista analítico.",
            styles["Body"],
        ),
        _spacer(0.3),
    ]

    for sinal in emp_sinais:
        grupo = rank1_df[rank1_df["Sinal"] == sinal].copy()
        if grupo.empty:
            continue

        elems.append(KeepTogether([
            Paragraph(f"<b>{sinal}</b>", styles["SubSection"]),
            _build_empate_subtable(grupo, score_col, styles),
            _spacer(0.2),
        ]))

    return elems


def _build_empate_subtable(grupo: pd.DataFrame, score_col: str, styles: dict) -> Table:
    """Tabela compacta de candidatos empatados para um único composto."""
    _score_cols = [c for c in ["Score Fragmentacao", "Score Lab", "Isotope Similarity"] if c in grupo.columns]
    headers = ["Candidato", score_col.replace("Score ", "Score ")] + _score_cols
    disp_headers = {
        score_col: "Score",
        "Score Fragmentacao": "Fragmentação",
        "Score Lab": "Score Lab",
        "Isotope Similarity": "Isótopo",
    }

    row_header = [Paragraph(disp_headers.get(h, h), styles["TableHeader"]) for h in ["Candidato"] + [score_col] + _score_cols]

    col_w_first = 5.5 * cm
    col_w_rest  = 1.8 * cm
    n_rest      = 1 + len(_score_cols)
    total_fixed = col_w_first + col_w_rest * n_rest
    if total_fixed < _USABLE_W:
        col_w_first += _USABLE_W - total_fixed
    col_widths = [col_w_first] + [col_w_rest] * n_rest

    rows = [row_header]
    for _, r in grupo.iterrows():
        try:
            sc = f"{float(r.get(score_col, 0) or 0):.1f}"
        except (TypeError, ValueError):
            sc = "—"

        data_row = [Paragraph(_trunc(str(r.get("Candidato") or "—"), 70), styles["TableCell"]),
                    Paragraph(sc, ParagraphStyle("SC", parent=styles["TableCell"], alignment=TA_CENTER))]
        for col in _score_cols:
            try:
                v = f"{float(r.get(col, 0) or 0):.1f}"
            except (TypeError, ValueError):
                v = "—"
            data_row.append(Paragraph(v, ParagraphStyle("EC", parent=styles["TableCell"], alignment=TA_CENTER)))
        rows.append(data_row)

    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), HexColor("#5a6e8c")),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, _CINZA_TBL]),
        ("GRID",          (0, 0), (-1, -1), 0.25, HexColor("#cccccc")),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
    ]))
    return tbl


def _sec_metodologia(ins: dict, batch_info: Optional[dict], styles: dict) -> list:
    """Nota metodológica: critérios IST, scores, disclaimer."""
    elems: list = []

    elems.append(Paragraph(
        "Este relatório foi gerado pelo <b>Omics ETL Pipeline</b>, sistema de processamento "
        "e identificação de compostos desenvolvido para o IST Ambiental / SENAI. "
        "Os resultados apresentados são produto de análise automática baseada nos dados "
        "do equipamento LC-MS/MS e de bases de dados científicas públicas (PubChem, ChEBI).",
        styles["Metodologia"],
    ))
    elems.append(_spacer(0.3))

    elems.append(Paragraph("Ranking hierárquico IST — ordem de prioridade dos critérios:", styles["SubSection"]))
    criterios = [
        ("1°", "Score de fragmentação MS/MS", "Correspondência com a biblioteca de fragmentos — maior poder biológico"),
        ("2°", "Score Lab",                   "Pontuação geral do software do instrumento"),
        ("3°", "Padrão isotópico",            "Similaridade com o padrão isotópico teórico"),
        ("4°", "Erro de massa (ppm)",          "Precisão de massa — menor erro é melhor"),
        ("5°", "Fórmula molecular",           "Desempate determinístico por ordem alfabética"),
        ("6°", "Empate humano",               "Sem critério automático — requer decisão do especialista"),
    ]
    crit_data = [
        [Paragraph(n, styles["TableCell"]),
         Paragraph(f"<b>{c}</b>", styles["TableCell"]),
         Paragraph(d, styles["TableCell"])]
        for n, c, d in criterios
    ]
    crit_tbl = Table(crit_data, colWidths=[0.8 * cm, 3.5 * cm, _USABLE_W - 4.3 * cm])
    crit_tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [white, _CINZA_TBL]),
        ("GRID",          (0, 0), (-1, -1), 0.25, HexColor("#d0d0d0")),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elems.append(crit_tbl)
    elems.append(_spacer(0.3))

    elems.append(Paragraph("Scores e métricas:", styles["SubSection"]))
    elems.append(Paragraph(
        "<b>Score Ranking (0–100):</b> média ponderada dos scores instrumentais "
        "(fragmentação 40% · lab 30% · isótopo 20% · massa 10%). "
        "Preservado como campo diagnóstico — não determina o Rank 1 no algoritmo atual.<br/>"
        "<b>Score Qualidade de Dados (0–100%):</b> percentual de campos de metadados externos "
        "preenchidos (fórmula, PubChem CID, peso molecular, ChEBI ID, classe química). "
        "Indica quão bem documentado é o candidato — não afeta o ranking.<br/>"
        "<b>Rank 1:</b> candidato mais compatível com o sinal segundo o algoritmo IST. "
        "Pode haver múltiplos Rank 1 em caso de empate.",
        styles["Metodologia"],
    ))
    elems.append(_spacer(0.3))

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
        elems.append(_spacer(0.3))

    elems.append(_hr(color=HexColor("#aaaaaa"), thickness=0.3))
    elems.append(Paragraph(
        "⚠ <i>Os resultados apresentados neste relatório foram gerados automaticamente pelo pipeline "
        "Omics ETL e representam hipóteses de identificação baseadas em correspondência espectral "
        "e dados de bases científicas públicas. Nenhuma identificação aqui listada deve ser "
        "considerada definitiva sem validação pelo especialista analítico responsável. "
        "Resultados em empate (coluna Emp. = ✓) requerem obrigatoriamente revisão manual.</i>",
        styles["Disclaimer"],
    ))

    return elems


# ---------------------------------------------------------------------------
# Montagem do documento completo
# ---------------------------------------------------------------------------

def _build_story(ins: dict, batch_info: Optional[dict], cobertura_ext: dict, styles: dict) -> list:
    story: list = []

    # 1 — Título
    story += _sec_titulo(ins, batch_info, styles)
    story.append(_spacer(0.4))

    # 2 — Resumo / métricas
    story.append(Paragraph("Resumo do Experimento", styles["SectionTitle"]))
    story += _sec_resumo(ins, cobertura_ext, styles)
    story.append(_spacer(0.4))

    # 3 — Leitura rápida
    story.append(Paragraph("Leitura Rápida do Experimento", styles["SectionTitle"]))
    story += _sec_insights(ins, styles)
    story.append(_spacer(0.4))

    # 4 — Critérios de desempate
    if not ins["criterio_counts"].empty:
        story.append(KeepTogether([
            Paragraph("Discriminabilidade por Critério de Desempate", styles["SectionTitle"]),
        ] + _sec_chart_criterios(ins, styles)))
        story.append(_spacer(0.4))

    # 5 — Distribuição de scores
    story.append(KeepTogether([
        Paragraph("Distribuição dos Scores de Identificação (Rank 1)", styles["SectionTitle"]),
    ] + _sec_chart_scores(ins, styles)))
    story.append(_spacer(0.4))

    # 6 — Perfil químico
    if not ins["classes_classif"].empty:
        story.append(KeepTogether([
            Paragraph("Perfil Químico do Experimento", styles["SectionTitle"]),
        ] + _sec_chart_classes(ins, cobertura_ext, styles)))
        story.append(_spacer(0.4))

    # 7 — Tabela Rank 1 (nova página — tabela longa)
    story.append(PageBreak())
    story.append(Paragraph(
        f"Candidatos Rank 1 por Composto  "
        f"<font size='9' color='#888888'>({ins['n_compostos']} compostos)</font>",
        styles["SectionTitle"],
    ))
    story += _sec_tabela_rank1(ins, styles)
    story.append(_spacer(0.4))

    # 8 — Compostos em empate
    if ins["n_empates"] > 0 and ins["_tem_empate"]:
        story.append(PageBreak())
        story.append(Paragraph(
            f"Compostos em Empate — Revisão Manual Necessária  "
            f"<font size='9' color='#888888'>({ins['n_empates']} compostos)</font>",
            styles["SectionTitle"],
        ))
        story += _sec_empates(ins, styles)
        story.append(_spacer(0.4))

    # 9 — Nota metodológica (nova página)
    story.append(PageBreak())
    story.append(Paragraph("Nota Metodológica", styles["SectionTitle"]))
    story += _sec_metodologia(ins, batch_info, styles)

    return story


# ---------------------------------------------------------------------------
# Ponto de entrada público
# ---------------------------------------------------------------------------

def gerar_relatorio_analitico(
    ins: dict,
    batch_info: Optional[dict] = None,
    cobertura_ext: Optional[dict] = None,
) -> bytes:
    """
    Gera o PDF do Relatório Analítico em memória e retorna os bytes.

    Args:
        ins:          Saída de src.reports.insights.computar_insights(df).
        batch_info:   Dict de metadata do batch (de listar_batches()); pode ser None.
        cobertura_ext: Saída de carregar_cobertura_externa(); pode ser None ou {}.

    Returns:
        Bytes do PDF gerado.

    Raises:
        ValueError: se ins estiver vazio.
    """
    if not ins:
        raise ValueError("Insights dict vazio — passe o resultado de computar_insights(df).")

    cobertura_ext = cobertura_ext or {}
    styles        = _make_styles()

    # Label do batch para o header de página
    if batch_info:
        d_raw  = (batch_info.get("iniciado_em") or "")[:10]
        b_label = f"Análise #{batch_info['id']}  ·  {d_raw}  ·  {batch_info.get('nome_ident', '')}"
    else:
        b_label = "Análise mais recente"

    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    hf_callback  = _make_header_footer(b_label, generated_at)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=_MARGIN_L,
        rightMargin=_MARGIN_R,
        topMargin=_MARGIN_T,
        bottomMargin=_MARGIN_B,
        title="Relatório Analítico de Identificação — Omics ETL",
        author="Omics ETL Pipeline · IST Ambiental / SENAI",
    )

    story = _build_story(ins, batch_info, cobertura_ext, styles)
    doc.build(story, onFirstPage=hf_callback, onLaterPages=hf_callback)

    return buf.getvalue()
