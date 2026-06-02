"""
Geração de gráficos matplotlib para inclusão em relatórios PDF.

Cada função retorna Optional[tuple[bytes, float]] onde:
  bytes — PNG serializado em memória
  float — aspect ratio (h / w) para cálculo de dimensão no PDF

Usa backend "Agg" (não interativo) — sem janela de GUI.
"""
import io
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

# ---------------------------------------------------------------------------
# Configurações globais de estilo — institutional, print-ready
# ---------------------------------------------------------------------------
plt.rcParams.update({
    "font.family":         "DejaVu Sans",
    "font.size":           9,
    "axes.titlesize":      10,
    "axes.labelsize":      8.5,
    "axes.spines.top":     False,
    "axes.spines.right":   False,
    "axes.grid":           True,
    "grid.color":          "#e0e0e0",
    "grid.linewidth":      0.5,
    "grid.alpha":          0.8,
    "figure.facecolor":    "white",
    "axes.facecolor":      "white",
    "savefig.facecolor":   "white",
    "figure.dpi":          150,
    "xtick.labelsize":     8,
    "ytick.labelsize":     8,
})

# Paleta institucional
_AZUL      = "#2e5d8e"
_AZUL_MED  = "#4472c4"
_VERDE     = "#5a9e6f"
_AMARELO   = "#f5a623"
_VERMELHO  = "#e57373"
_CINZA     = "#9e9e9e"
_CINZA_TXT = "#444444"

_FIG_W = 6.5  # largura padrão das figuras em inches


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_png(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _bar_values(ax, bars, fmt="{:.0f}", offset_factor=0.02, **kwargs):
    """Anota valor no extremo de cada barra horizontal."""
    max_val = max((b.get_width() for b in bars), default=1)
    for bar in bars:
        val = bar.get_width()
        ax.text(
            val + max_val * offset_factor,
            bar.get_y() + bar.get_height() / 2,
            fmt.format(val),
            va="center",
            ha="left",
            fontsize=8,
            color=_CINZA_TXT,
            **kwargs,
        )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def chart_criterios(criterio_counts: pd.DataFrame) -> Optional[tuple[bytes, float]]:
    """
    Gráfico de barras horizontais: distribuição dos critérios de desempate IST.
    Colorido por nível hierárquico (fragmentação=azul escuro, empate=vermelho).
    """
    if criterio_counts.empty:
        return None

    n_rows  = len(criterio_counts)
    fig_h   = max(2.8, n_rows * 0.58)
    fig, ax = plt.subplots(figsize=(_FIG_W, fig_h))

    colors = criterio_counts["cor"].tolist()
    bars   = ax.barh(
        criterio_counts["label"],
        criterio_counts["n"],
        color=colors,
        height=0.62,
        edgecolor="none",
        alpha=0.9,
    )
    _bar_values(ax, bars)

    ax.set_xlabel("Compostos com Rank 1 determinado por este critério", fontsize=8)
    ax.set_xlim(0, criterio_counts["n"].max() * 1.22)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=8.5)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)

    fig.tight_layout(pad=0.5)
    return _to_png(fig), fig_h / _FIG_W


def chart_scores(rank1_unico: pd.DataFrame, score_col: str) -> Optional[tuple[bytes, float]]:
    """
    Histograma dos scores de identificação (Rank 1).
    Barras coloridas por tier: vermelho (<45) / azul (45–80) / verde (≥80).
    Linha vermelha pontilhada no limiar 80.
    """
    if rank1_unico.empty:
        return None

    scores = pd.to_numeric(rank1_unico[score_col], errors="coerce").dropna()
    if scores.empty:
        return None

    fig_h   = 3.4
    fig, ax = plt.subplots(figsize=(_FIG_W, fig_h))

    bins = list(range(0, 105, 10))
    n, edges, patches = ax.hist(scores, bins=bins, edgecolor="white", linewidth=0.6, zorder=3)

    # Coloração por tier
    for patch, left in zip(patches, edges[:-1]):
        if left >= 80:
            patch.set_facecolor(_VERDE)
        elif left >= 45:
            patch.set_facecolor(_AZUL_MED)
        else:
            patch.set_facecolor(_VERMELHO)
        patch.set_alpha(0.88)

    # Linha de referência 80
    ax.axvline(80, color="#c0392b", linewidth=1.3, linestyle="--", alpha=0.75, zorder=4)

    # Legenda manual
    legenda = [
        mpatches.Patch(facecolor=_VERMELHO,  label="Baixa confiança (< 45)",  alpha=0.88),
        mpatches.Patch(facecolor=_AZUL_MED,  label="Moderada (45–80)",         alpha=0.88),
        mpatches.Patch(facecolor=_VERDE,     label="Alta confiança (≥ 80)",    alpha=0.88),
    ]
    ax.legend(handles=legenda, fontsize=7.5, loc="upper left", framealpha=0.9)

    ax.set_xlabel("Score de identificação — Rank 1 (0–100)", fontsize=8)
    ax.set_ylabel("Compostos", fontsize=8)
    ax.set_xlim(-2, 102)
    ax.set_xticks(range(0, 110, 10))
    ax.set_axisbelow(True)

    fig.tight_layout(pad=0.5)
    return _to_png(fig), fig_h / _FIG_W


def chart_classes(classes_classif: pd.DataFrame) -> Optional[tuple[bytes, float]]:
    """
    Gráfico de barras horizontais: classes químicas dos Rank 1 (top 10).
    """
    if classes_classif.empty:
        return None

    top     = classes_classif.head(10).sort_values("Frequência", ascending=True)
    n_rows  = len(top)
    fig_h   = max(2.8, n_rows * 0.56)
    fig, ax = plt.subplots(figsize=(_FIG_W, fig_h))

    bars = ax.barh(
        top["Classe química"],
        top["Frequência"],
        color=_VERDE,
        height=0.62,
        edgecolor="none",
        alpha=0.85,
    )
    _bar_values(ax, bars)

    ax.set_xlabel("Compostos Rank 1 nesta classe", fontsize=8)
    ax.set_xlim(0, top["Frequência"].max() * 1.22)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=8.5)
    ax.grid(axis="x")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)

    fig.tight_layout(pad=0.5)
    return _to_png(fig), fig_h / _FIG_W
