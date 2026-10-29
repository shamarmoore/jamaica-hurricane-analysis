"""Build the processed tables used by the notebooks and the Power BI report.

Usage:
    python scripts/build_dataset.py            # use cached raw files
    python scripts/build_dataset.py --refresh  # re-download HURDAT2 and ONI first
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jhurricane import config, features, hurdat  # noqa: E402


def main(refresh: bool) -> None:
    if refresh or not config.HURDAT2_FILE.exists():
        print("Downloading HURDAT2 ...")
        hurdat.download()
    if refresh or not config.ONI_FILE.exists():
        print("Downloading ONI ...")
        config.ONI_FILE.write_text(requests.get(config.ONI_URL, timeout=60).text, encoding="utf-8")

    fixes = hurdat.parse()
    print(f"Parsed {len(fixes):,} fixes for {fixes['storm_id'].nunique():,} storms "
          f"({fixes['year'].min()}-{fixes['year'].max()})")

    oni = features.load_oni()
    storms = features.build_storm_table(fixes)
    season = features.build_season_table(storms, fixes, oni)
    points = features.build_track_points(fixes, storms)
    pathways = features.build_pathways(fixes, storms)

    impacts = pd.read_csv(config.IMPACTS_FILE)
    ids = storms[["storm_id", "storm_name", "year"]]
    impacts = impacts.merge(ids, on=["storm_name", "year"], how="left")
    missing = impacts.loc[impacts["storm_id"].isna(), "storm_name"].tolist()
    if missing:
        raise ValueError(f"Impact rows with no matching track: {missing}")

    oni_aso = features.oni_peak_season(oni)
    storms = storms.merge(oni_aso, on="year", how="left")

    config.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    storms.to_csv(config.DATA_PROCESSED / "storms.csv", index=False)
    season.to_csv(config.DATA_PROCESSED / "seasons.csv", index=False)
    points.to_csv(config.DATA_PROCESSED / "track_points.csv", index=False)
    pathways.to_csv(config.DATA_PROCESSED / "pathways.csv", index=False)
    impacts.to_csv(config.DATA_PROCESSED / "impacts.csv", index=False)
    oni.to_csv(config.DATA_PROCESSED / "oni_monthly.csv", index=False)

    near = storms[storms["is_near"]]
    print(f"Storms within {config.SEARCH_RADIUS_NM} nm: {len(storms):,}")
    print(f"Storms at TS+ strength within {config.NEAR_RADIUS_NM} nm: {len(near):,} "
          f"({near['is_hurricane_near'].sum()} hurricanes, {near['is_major_near'].sum()} major)")
    print(f"Jamaica landfalls: {storms['jamaica_landfall'].sum()}")
    print(f"Wrote tables to {config.DATA_PROCESSED}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="re-download source data")
    main(parser.parse_args().refresh)
