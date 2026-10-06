"""Shared matplotlib styling and map helpers so every figure reads as one set."""
from __future__ import annotations

import json

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MplPolygon
from shapely.geometry import shape

from . import config

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
LAND = "#ecebe6"
LAND_EDGE = "#c3c2b7"

BLUE = "#2a78d6"     # slot 1
ORANGE = "#eb6834"   # slot 2 (also used as the single "highlight" colour)
AQUA = "#1baf7a"     # slot 3
GRAY = "#b9b8b1"     # de-emphasised context

# Ordinal ramp for intensity (Saffir-Simpson is ordered, so one hue light -> dark).
INTENSITY = {
    "TD": "#cde2fb",
    "TS": "#86b6ef",
    "Cat 1": "#5598e7",
    "Cat 2": "#2a78d6",
    "Cat 3": "#1c5cab",
    "Cat 4": "#104281",
    "Cat 5": "#0d366b",
}
ENSO = {"La Nina": BLUE, "Neutral": GRAY, "El Nino": ORANGE}


def set_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE,
        "axes.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "figure.dpi": 110,
        "savefig.dpi": 160,
        "savefig.bbox": "tight",
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
        "font.size": 10.5,
        "text.color": INK,
        "axes.labelcolor": INK_2,
        "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.titlepad": 24,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "axes.axisbelow": True,
        "grid.color": GRID,
        "grid.linewidth": 0.7,
        "grid.linestyle": "-",
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "xtick.labelcolor": INK_2,
        "ytick.labelcolor": INK_2,
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "legend.frameon": False,
        "lines.linewidth": 2,
    })


def subtitle(ax, text: str) -> None:
    """Grey one-line subtitle under a left-aligned title."""
    ax.annotate(text, xy=(0, 1), xycoords="axes fraction", xytext=(0, 4),
                textcoords="offset points", fontsize=9.5, color=INK_2, va="bottom")


def source_note(fig, text: str = "Source: NOAA NHC HURDAT2 (1851-2025). Analysis: Shamar Moore.", y: float = -0.02) -> None:
    fig.text(0.01, y, text, fontsize=8, color=MUTED, ha="left", va="top")


def _add_geom(ax, geom, **kw):
    polys = geom.geoms if hasattr(geom, "geoms") else [geom]
    for p in polys:
        if p.geom_type == "Polygon":
            ax.add_patch(MplPolygon(list(p.exterior.coords), closed=True, **kw))


def draw_basemap(ax, extent=(-86, -66, 12, 24), highlight_jamaica=True) -> None:
    with open(config.BASEMAP_FILE, encoding="utf-8") as fh:
        feats = json.load(fh)["features"]
    for f in feats:
        geom = shape(f["geometry"])
        is_jam = f["properties"]["name"] == "Jamaica"
        _add_geom(ax, geom,
                  facecolor="#d9d8d1" if (is_jam and highlight_jamaica) else LAND,
                  edgecolor=INK_2 if (is_jam and highlight_jamaica) else LAND_EDGE,
                  linewidth=0.8 if is_jam else 0.5, zorder=1)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect(1 / 0.95)  # rough cos(lat) correction at ~18 N
    ax.grid(False)
    ax.set_facecolor("#f4f7fb")
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])
