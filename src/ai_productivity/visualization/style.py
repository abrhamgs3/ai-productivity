"""
Shared matplotlib style for publication-quality figures.

Usage
-----
    from ai_productivity.visualization.style import apply_style, COLORS

    apply_style()          # call once before creating any figure
    ax.plot(..., color=COLORS["blue"])

Why a style module?
-------------------
Without a shared style, each figure independently sets fonts, sizes, and
colors. A reviewer asking for "all figures in 10pt Times" means editing
every file. With a style module, you change one line.

Design choices
--------------
- No figure titles. Titles belong in LaTeX ``\\caption{}`` commands, not
  embedded in the image. Journals enforce this.
- 6.5-inch width fits a standard one-column manuscript at 72pt margins.
  For two-column layout use ``WIDTH_NARROW = 3.25``.
- 300 DPI is the minimum for most print journals; we default to 300.
- Color palette from ColorBrewer 2-class diverging (colorblind-safe).
"""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

WIDTH_FULL   = 6.5   # inches — one-column manuscript width
WIDTH_NARROW = 3.25  # inches — two-column half-width
DPI          = 300

# ---------------------------------------------------------------------------
# Color palette (ColorBrewer RdBu, colorblind-safe)
# ---------------------------------------------------------------------------

COLORS: dict[str, str] = {
    "blue":       "#2166ac",   # primary series / positive
    "red":        "#d6604d",   # secondary series / negative
    "grey":       "#636363",   # neutral / zero line
    "light_blue": "#92c5de",   # confidence band fill
    "light_red":  "#f4a582",   # secondary band fill
    "black":      "#1a1a1a",   # text / axis
}

# ---------------------------------------------------------------------------
# rcParams
# ---------------------------------------------------------------------------

_RC = {
    # Font
    "font.family":       "serif",
    "font.serif":        ["Times New Roman", "DejaVu Serif", "serif"],
    "font.size":         10,
    "axes.titlesize":    10,
    "axes.labelsize":    10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   9,

    # Lines
    "lines.linewidth":   1.5,
    "axes.linewidth":    0.8,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,

    # Spines — remove top/right for a clean look
    "axes.spines.top":   False,
    "axes.spines.right": False,

    # Grid — light horizontal only
    "axes.grid":         True,
    "axes.grid.axis":    "y",
    "grid.color":        "#e0e0e0",
    "grid.linewidth":    0.6,
    "grid.linestyle":    "-",

    # Figure
    "figure.dpi":        DPI,
    "savefig.dpi":       DPI,
    "savefig.bbox":      "tight",
    "savefig.pad_inches": 0.05,

    # Legend
    "legend.frameon":    False,
    "legend.borderpad":  0.0,
}


def apply_style() -> None:
    """Apply the publication rcParams globally.

    Call once at the top of any figure-generating script or at the start
    of a pipeline run.  Safe to call multiple times.
    """
    mpl.rcParams.update(_RC)


def figure(width: float = WIDTH_FULL, aspect: float = 0.55, **kwargs):
    """Create a figure pre-sized for the manuscript.

    Parameters
    ----------
    width:
        Figure width in inches.  Default is full-column width (6.5").
    aspect:
        Height / width ratio.  Default 0.55 gives a 16:9-ish shape.
    **kwargs:
        Passed to ``plt.subplots``.

    Returns
    -------
    (fig, ax)
    """
    apply_style()
    height = width * aspect
    return plt.subplots(figsize=(width, height), **kwargs)
