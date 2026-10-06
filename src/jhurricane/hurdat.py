"""Download and parse NOAA HURDAT2 best-track data."""
from __future__ import annotations

import numpy as np
import pandas as pd
import requests

from . import config


def download(url: str = config.HURDAT2_URL, dest=config.HURDAT2_FILE) -> None:
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(resp.text, encoding="utf-8")


def saffir_simpson(wind_kt):
    """Map max sustained wind (kt) to a Saffir-Simpson label. Works on scalars or arrays."""
    bins = [-np.inf, 34, 64, 83, 96, 113, 137, np.inf]
    labels = config.CATEGORY_ORDER
    out = pd.cut(pd.Series(wind_kt, dtype="float"), bins=bins, labels=labels, right=False)
    return out.astype("object").where(out.notna(), None)


def _coord(text: str) -> float:
    value = float(text[:-1])
    return -value if text[-1] in "SW" else value


def parse(path=config.HURDAT2_FILE) -> pd.DataFrame:
    """Parse HURDAT2 into one row per best-track fix.

    The file alternates header lines (``AL092004, IVAN, 94,``) with fix lines.
    Missing values are coded as -999 (pressure) or -99 (wind).
    """
    rows = []
    storm_id = name = None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 8:  # header line
                storm_id, name = parts[0], parts[1]
                continue
            wind = int(parts[6])
            pressure = int(parts[7])
            rows.append(
                {
                    "storm_id": storm_id,
                    "storm_name": name,
                    "datetime": pd.Timestamp(
                        int(parts[0][:4]), int(parts[0][4:6]), int(parts[0][6:8]),
                        int(parts[1][:2]), int(parts[1][2:4]),
                    ),
                    "record_id": parts[2],
                    "status": parts[3],
                    "lat": _coord(parts[4]),
                    "lon": _coord(parts[5]),
                    "wind_kt": np.nan if wind < 0 else wind,
                    "pressure_mb": np.nan if pressure < 0 else pressure,
                }
            )
    df = pd.DataFrame(rows)
    df["year"] = df["datetime"].dt.year
    df["category"] = saffir_simpson(df["wind_kt"]).values
    df["is_landfall"] = df["record_id"].eq("L")
    return df


def interpolate_hourly(track: pd.DataFrame) -> pd.DataFrame:
    """Linearly interpolate a single storm's track to hourly resolution.

    Six-hourly fixes can be ~100 nm apart for a fast mover, so closest-approach
    distances computed on raw fixes are biased high. Hourly interpolation fixes that.
    """
    t = track.drop_duplicates("datetime").set_index("datetime")[["lat", "lon", "wind_kt", "pressure_mb"]]
    idx = pd.date_range(t.index.min().ceil("h"), t.index.max().floor("h"), freq="h")
    out = t.reindex(t.index.union(idx)).interpolate(method="time", limit_area="inside").loc[idx]
    out.index.name = "datetime"
    return out.reset_index()
