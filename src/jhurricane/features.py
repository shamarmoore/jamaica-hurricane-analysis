"""Turn raw best-track fixes into Jamaica-centred storm, season and point tables."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, geo, hurdat

TROPICAL = {"TS", "HU", "SS", "TD", "SD"}


def load_oni(path=config.ONI_FILE) -> pd.DataFrame:
    """NOAA CPC Oceanic Nino Index, one row per overlapping 3-month season."""
    oni = pd.read_csv(path, sep=r"\s+")
    oni.columns = ["season", "year", "total", "anom"]
    return oni


def enso_phase(anom):
    return np.select([anom >= 0.5, anom <= -0.5], ["El Nino", "La Nina"], "Neutral")


def oni_peak_season(oni: pd.DataFrame) -> pd.DataFrame:
    """ONI for Aug-Sep-Oct, the core of the Caribbean hurricane season."""
    aso = oni.loc[oni["season"] == "ASO", ["year", "anom"]].rename(columns={"anom": "oni_aso"})
    aso["enso_phase"] = enso_phase(aso["oni_aso"])
    return aso


def basin_season_stats(fixes: pd.DataFrame) -> pd.DataFrame:
    """Named storms and Accumulated Cyclone Energy for the whole Atlantic, per year."""
    synoptic = fixes[fixes["datetime"].dt.hour.isin([0, 6, 12, 18]) & (fixes["datetime"].dt.minute == 0)]
    ace_rows = synoptic[synoptic["status"].isin(["TS", "HU", "SS"]) & (synoptic["wind_kt"] >= 34)]
    ace = (ace_rows["wind_kt"] ** 2).groupby(ace_rows["year"]).sum() / 1e4
    named = ace_rows.groupby("year")["storm_id"].nunique()
    return pd.DataFrame({"basin_named_storms": named, "basin_ace": ace.round(1)}).rename_axis("year").reset_index()


def _storm_summary(storm_id: str, fixes: pd.DataFrame) -> dict | None:
    hourly = hurdat.interpolate_hourly(fixes)
    if hourly.empty:
        return None
    hourly["dist_nm"] = geo.distance_to_coast_nm(hourly["lat"], hourly["lon"])
    i_min = hourly["dist_nm"].idxmin()
    closest = hourly.loc[i_min]
    near = hourly[hourly["dist_nm"] <= config.NEAR_RADIUS_NM]

    # Where the storm came from: position 24 h before closest approach, seen from Jamaica.
    t0 = closest["datetime"]
    before = hourly[hourly["datetime"] <= t0 - pd.Timedelta(hours=24)]
    origin = before.iloc[-1] if len(before) else hourly.iloc[0]
    approach_bearing = geo.bearing_deg(*config.JAMAICA_CENTER, origin["lat"], origin["lon"])

    # Motion at closest approach, from the hours either side.
    nxt = hourly[hourly["datetime"] >= t0 + pd.Timedelta(hours=3)]
    prv = hourly[hourly["datetime"] <= t0 - pd.Timedelta(hours=3)]
    a = prv.iloc[-1] if len(prv) else closest
    b = nxt.iloc[0] if len(nxt) else closest
    hours = max((b["datetime"] - a["datetime"]).total_seconds() / 3600, 1)
    speed = geo.haversine_nm(a["lat"], a["lon"], b["lat"], b["lon"]) / hours
    heading = geo.bearing_deg(a["lat"], a["lon"], b["lat"], b["lon"])

    # Rapid intensification (>= 30 kt in 24 h) during the 72 h before closest approach.
    window = fixes[(fixes["datetime"] <= t0) & (fixes["datetime"] >= t0 - pd.Timedelta(hours=72))]
    w = window.set_index("datetime")["wind_kt"].dropna()
    ri_24h = 0.0
    for t, v in w.items():
        prior = w[w.index <= t - pd.Timedelta(hours=24)]
        if len(prior):
            ri_24h = max(ri_24h, v - prior.iloc[-1])

    landfall_fix = fixes[fixes["is_landfall"]]
    landfall_jam = bool(
        (closest["dist_nm"] == 0)
        or (len(landfall_fix) and (geo.distance_to_coast_nm(landfall_fix["lat"], landfall_fix["lon"]) <= 5).any())
    )

    return {
        "storm_id": storm_id,
        "storm_name": fixes["storm_name"].iat[0],
        "year": int(fixes["year"].iat[0]),
        "closest_datetime": t0,
        "closest_month": t0.month,
        "closest_distance_nm": round(float(closest["dist_nm"]), 1),
        "closest_lat": round(float(closest["lat"]), 2),
        "closest_lon": round(float(closest["lon"]), 2),
        "wind_at_closest_kt": closest["wind_kt"],
        "pressure_at_closest_mb": closest["pressure_mb"],
        "max_wind_near_kt": near["wind_kt"].max() if len(near) else np.nan,
        "min_pressure_near_mb": near["pressure_mb"].min() if len(near) else np.nan,
        "hours_near": int(len(near)),
        "approach_from": str(geo.compass(approach_bearing)),
        "approach_bearing_deg": round(float(approach_bearing)),
        "heading_deg": round(float(heading)),
        "forward_speed_kt": round(float(speed), 1),
        "max_24h_intensification_kt": ri_24h,
        "rapid_intensification": ri_24h >= 30,
        "jamaica_landfall": landfall_jam,
        "lifetime_peak_wind_kt": fixes["wind_kt"].max(),
        "lifetime_min_pressure_mb": fixes["pressure_mb"].min(),
    }


def build_storm_table(fixes: pd.DataFrame) -> pd.DataFrame:
    """One row per storm that came within SEARCH_RADIUS_NM of Jamaica."""
    fixes = fixes.copy()
    fixes["dist_nm"] = geo.distance_to_coast_nm(fixes["lat"], fixes["lon"])
    candidates = fixes.loc[fixes["dist_nm"] <= config.SEARCH_RADIUS_NM + 150, "storm_id"].unique()
    rows = [_storm_summary(sid, g) for sid, g in fixes[fixes["storm_id"].isin(candidates)].groupby("storm_id")]
    storms = pd.DataFrame([r for r in rows if r])
    storms = storms[storms["closest_distance_nm"] <= config.SEARCH_RADIUS_NM].copy()
    interp_cols = ["wind_at_closest_kt", "pressure_at_closest_mb", "max_wind_near_kt",
                   "min_pressure_near_mb", "max_24h_intensification_kt"]
    storms[interp_cols] = storms[interp_cols].round()

    storms["category_near_jamaica"] = hurdat.saffir_simpson(storms["max_wind_near_kt"]).values
    storms["is_near"] = storms["max_wind_near_kt"].ge(34)  # at least TS strength within 50 nm
    storms["is_hurricane_near"] = storms["max_wind_near_kt"].ge(64)
    storms["is_major_near"] = storms["max_wind_near_kt"].ge(96)
    storms["distance_band"] = pd.cut(
        storms["closest_distance_nm"], [-1, 0, 50, 100, 200, 400, 600],
        labels=["Landfall", "1-50 nm", "51-100 nm", "101-200 nm", "201-400 nm", "401-600 nm"],
    ).astype(str)
    storms["decade"] = storms["year"] // 10 * 10
    storms["era"] = np.select(
        [storms["year"] >= config.SATELLITE_ERA_START, storms["year"] >= config.MODERN_ERA_START],
        ["Satellite (1966+)", "Recon (1950-65)"], "Historical (pre-1950)",
    )
    storms["storm_label"] = storms["storm_name"].str.title() + " (" + storms["year"].astype(str) + ")"
    # Pre-1950 storms are mostly "UNNAMED"; add the ATCF number so every label is unique.
    unnamed = storms["storm_name"].eq("UNNAMED")
    storms.loc[unnamed, "storm_label"] = ("Unnamed #" + storms.loc[unnamed, "storm_id"].str[2:4]
                                          + " (" + storms.loc[unnamed, "year"].astype(str) + ")")
    return storms.sort_values("closest_datetime").reset_index(drop=True)


def build_season_table(storms: pd.DataFrame, fixes: pd.DataFrame, oni: pd.DataFrame) -> pd.DataFrame:
    near = storms[storms["is_near"]]
    years = pd.DataFrame({"year": range(int(fixes["year"].min()), int(fixes["year"].max()) + 1)})
    counts = near.groupby("year").agg(
        storms_near=("storm_id", "count"),
        hurricanes_near=("is_hurricane_near", "sum"),
        majors_near=("is_major_near", "sum"),
        landfalls=("jamaica_landfall", "sum"),
        max_wind_near_kt=("max_wind_near_kt", "max"),
    )
    season = years.merge(counts, on="year", how="left").merge(basin_season_stats(fixes), on="year", how="left")
    counts_cols = ["storms_near", "hurricanes_near", "majors_near", "landfalls", "basin_named_storms"]
    season[counts_cols] = season[counts_cols].fillna(0).astype(int)
    season["basin_ace"] = season["basin_ace"].fillna(0.0)
    season = season.merge(oni_peak_season(oni), on="year", how="left")
    season["enso_phase"] = season["enso_phase"].fillna("No data (pre-1950)")
    season["decade"] = season["year"] // 10 * 10
    return season


PATHWAYS = {
    # pathway: (label, approach sectors it covers, sort order)
    "E": ("From the east", {"E"}, 1),
    "SE": ("From the south-east", {"SE"}, 2),
    "S": ("From the south", {"S"}, 3),
    "W": ("From the south-west and west", {"SW", "W"}, 4),
    "N": ("From the north", {"N", "NE", "NW"}, 5),
}


def build_pathways(fixes: pd.DataFrame, storms: pd.DataFrame, before_h: int = 48, after_h: int = 24) -> pd.DataFrame:
    """The typical route into Jamaica for each approach direction, with each route's share of storms.

    Every near storm's hourly track is aligned on its closest approach, then positions are
    averaged across the storms in a pathway at each 3-hour offset. Thin sectors are merged so
    every line stands for several storms rather than one storm's quirks.
    """
    near = storms[storms["is_near"]]
    sector_to_pathway = {s: p for p, (_, sectors, _) in PATHWAYS.items() for s in sectors}
    offsets = np.arange(-before_h, after_h + 1, 3)
    rows = []
    for _, storm in near.iterrows():
        hourly = hurdat.interpolate_hourly(fixes[fixes["storm_id"] == storm["storm_id"]])
        hours = (hourly["datetime"] - pd.Timestamp(storm["closest_datetime"])).dt.total_seconds() / 3600
        aligned = hourly.assign(offset_h=hours.round().astype(int))
        aligned = aligned[aligned["offset_h"].isin(offsets)]
        rows.append(aligned.assign(pathway=sector_to_pathway[storm["approach_from"]], storm_id=storm["storm_id"]))
    tracks = pd.concat(rows)

    paths = tracks.groupby(["pathway", "offset_h"], as_index=False)[["lat", "lon"]].mean()
    paths[["lat", "lon"]] = (paths.groupby("pathway")[["lat", "lon"]]
                             .transform(lambda s: s.rolling(5, center=True, min_periods=1).mean()).round(3))
    counts = tracks.groupby("pathway")["storm_id"].nunique()
    paths["storms"] = paths["pathway"].map(counts)
    paths["share"] = (paths["storms"] / len(near)).round(4)
    paths["pathway_label"] = paths["pathway"].map(lambda p: PATHWAYS[p][0])
    paths["sort_order"] = paths["pathway"].map(lambda p: PATHWAYS[p][2])
    paths["point_seq"] = paths.groupby("pathway").cumcount()
    cols = ["pathway", "pathway_label", "sort_order", "storms", "share", "point_seq", "offset_h", "lat", "lon"]
    return paths[cols].sort_values(["sort_order", "point_seq"]).reset_index(drop=True)


def build_track_points(fixes: pd.DataFrame, storms: pd.DataFrame) -> pd.DataFrame:
    """Best-track fixes for the retained storms, for mapping (incl. Power BI)."""
    pts = fixes[fixes["storm_id"].isin(storms["storm_id"])].copy()
    pts["dist_nm"] = geo.distance_to_coast_nm(pts["lat"], pts["lon"]).round(1)
    pts = pts[pts["lon"].between(-100, -50) & pts["lat"].between(5, 40)]
    pts["within_near_radius"] = pts["dist_nm"] <= config.NEAR_RADIUS_NM
    pts["point_seq"] = pts.groupby("storm_id").cumcount()
    cols = ["storm_id", "point_seq", "datetime", "status", "record_id", "lat", "lon",
            "wind_kt", "pressure_mb", "category", "dist_nm", "within_near_radius"]
    return pts[cols].reset_index(drop=True)
