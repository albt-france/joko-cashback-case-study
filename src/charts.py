"""Chart helpers for the report: one visual style for every page (matplotlib, static PNG).

Colours: blue = Joko (or the focus series), grey = competitors / comparison,
red = alerts only, dashed lines = thresholds or reference values.
"""
import base64
import io

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BLUE = "#2A78D6"
BLUE_LIGHT = "#86B6EF"
GREY = "#A3A099"
GREY_LIGHT = "#D9D7D0"
RED = "#D03B3B"
INK = "#0B0B0B"
INK2 = "#52514E"
MUTED = "#898781"
GRID = "#E1E0D9"
CARD = "#FFFFFF"

plt.rcParams.update({
    "font.family": "Segoe UI", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": CARD, "axes.facecolor": CARD, "legend.frameon": False,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": INK, "axes.titlelocation": "left",
})


def fig(w=6.0, h=3.2):
    f, ax = plt.subplots(figsize=(w, h), dpi=200)
    return f, ax


def to_img(f):
    """Return an <img> tag with the figure embedded as base64 PNG."""
    buf = io.BytesIO()
    f.tight_layout()
    f.savefig(buf, format="png", dpi=200, facecolor=CARD)
    plt.close(f)
    data = base64.b64encode(buf.getvalue()).decode()
    return f'<img src="data:image/png;base64,{data}"/>'


def hbar(ax, labels, values, colors, fmt="{:.1f}", xlabel=None):
    """Horizontal bars with a value label at the end of each bar (identity never colour-only)."""
    y = range(len(labels))
    ax.barh(list(y), values, color=colors, height=0.62, edgecolor=CARD, linewidth=1)
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    vmax = max(values) if len(values) else 1
    for i, v in enumerate(values):
        ax.text(v + vmax * 0.01, i, fmt.format(v), va="center", fontsize=9, color=INK2)
    ax.set_xlim(0, vmax * 1.15)
    ax.tick_params(axis="y", length=0, labelcolor=INK2)
    if xlabel:
        ax.set_xlabel(xlabel)
