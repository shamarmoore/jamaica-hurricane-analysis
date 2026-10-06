"""Approach-risk model: will a storm currently 150-600 nm away pass within 100 nm of Jamaica?

Each training row is one 6-hourly best-track fix. Features describe the storm *at that
moment* (position relative to Jamaica, motion, intensity, season, ENSO), and the label
looks ahead 72 hours along the actual track. Rows from the same storm are strongly
correlated, so evaluation always splits by storm, never by row.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, features, geo, hurdat

HORIZON_H = 72
MIN_DIST_NM, MAX_DIST_NM = 150, 600

FEATURES = [
    "dist_nm", "rel_lat", "rel_lon", "bearing_sin", "bearing_cos",
    "heading_sin", "heading_cos", "speed_kt", "closing_speed_kt",
    "wind_kt", "wind_change_24h", "month", "oni",
    "persistence_min_dist_nm",
]


def _persistence_min_distance(lat, lon, heading, speed_kt, hours=HORIZON_H, step=3):
    """Extrapolate current motion in a straight line and return the closest distance to the coast."""
    h = np.radians(heading)
    best = geo.distance_to_coast_nm(lat, lon)
    for t in range(step, hours + 1, step):
        d = speed_kt * t
        dlat = d * np.cos(h) / 60.0
        dlon = d * np.sin(h) / (60.0 * np.cos(np.radians(lat)))
        best = np.minimum(best, geo.distance_to_coast_nm(lat + dlat, lon + dlon))
    return best


def build_dataset(fixes: pd.DataFrame, oni: pd.DataFrame, start_year: int = config.MODERN_ERA_START) -> pd.DataFrame:
    fx = fixes[(fixes["year"] >= start_year) & fixes["datetime"].dt.minute.eq(0)
               & fixes["datetime"].dt.hour.isin([0, 6, 12, 18])].copy()
    fx["dist_nm"] = geo.distance_to_coast_nm(fx["lat"], fx["lon"])
    keep = fx.groupby("storm_id")["dist_nm"].transform("min") <= MAX_DIST_NM
    fx = fx[keep].sort_values(["storm_id", "datetime"])

    rows = []
    for sid, g in fx.groupby("storm_id"):
        g = g.reset_index(drop=True)
        hourly = hurdat.interpolate_hourly(g)
        hourly["dist_nm"] = geo.distance_to_coast_nm(hourly["lat"], hourly["lon"])
        hd = hourly.set_index("datetime")["dist_nm"]
        for i in range(1, len(g)):
            cur, prev = g.loc[i], g.loc[i - 1]
            if not (MIN_DIST_NM <= cur["dist_nm"] <= MAX_DIST_NM):
                continue
            if cur["status"] not in features.TROPICAL:
                continue
            hrs = (cur["datetime"] - prev["datetime"]).total_seconds() / 3600
            if hrs <= 0:
                continue
            future = hd[(hd.index > cur["datetime"]) & (hd.index <= cur["datetime"] + pd.Timedelta(hours=HORIZON_H))]
            day_ago = g[g["datetime"] <= cur["datetime"] - pd.Timedelta(hours=24)]
            rows.append({
                "storm_id": sid,
                "storm_name": cur["storm_name"],
                "year": cur["year"],
                "datetime": cur["datetime"],
                "lat": cur["lat"],
                "lon": cur["lon"],
                "dist_nm": cur["dist_nm"],
                "heading": geo.bearing_deg(prev["lat"], prev["lon"], cur["lat"], cur["lon"]),
                "speed_kt": geo.haversine_nm(prev["lat"], prev["lon"], cur["lat"], cur["lon"]) / hrs,
                "closing_speed_kt": (prev["dist_nm"] - cur["dist_nm"]) / hrs,
                "wind_kt": cur["wind_kt"],
                "wind_change_24h": cur["wind_kt"] - day_ago["wind_kt"].iloc[-1] if len(day_ago) else 0.0,
                "month": cur["datetime"].month,
                "future_min_dist_nm": future.min() if len(future) else np.nan,
            })

    df = pd.DataFrame(rows).dropna(subset=["future_min_dist_nm", "wind_kt"])
    bearing = geo.bearing_deg(*config.JAMAICA_CENTER, df["lat"], df["lon"])
    df["rel_lat"] = df["lat"] - config.JAMAICA_CENTER[0]
    df["rel_lon"] = df["lon"] - config.JAMAICA_CENTER[1]
    df["bearing_sin"], df["bearing_cos"] = np.sin(np.radians(bearing)), np.cos(np.radians(bearing))
    df["heading_sin"], df["heading_cos"] = np.sin(np.radians(df["heading"])), np.cos(np.radians(df["heading"]))
    df["persistence_min_dist_nm"] = _persistence_min_distance(df["lat"].values, df["lon"].values,
                                                              df["heading"].values, df["speed_kt"].values)

    # ONI for the overlapping 3-month season centred on the fix's month.
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    oni_lookup = oni.assign(month=oni["season"].map({s: i + 1 for i, s in enumerate(seasons)}))
    oni_lookup = oni_lookup.set_index(["year", "month"])["anom"]
    df["oni"] = [oni_lookup.get((y, m), np.nan) for y, m in zip(df["year"], df["month"])]
    df["oni"] = df["oni"].fillna(0.0)

    df["label"] = (df["future_min_dist_nm"] <= config.NEAR_RADIUS_NM).astype(int)
    return df.reset_index(drop=True)
