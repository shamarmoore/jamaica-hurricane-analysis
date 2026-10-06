"""Project-wide paths and constants."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"

# NOAA NHC Atlantic best track (HURDAT2). Release of 23 Sep 2026 covers 1851-2025.
HURDAT2_URL = "https://www.nhc.noaa.gov/data/hurdat/hurdat2-1851-2025-092326.txt"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"

HURDAT2_FILE = DATA_RAW / "hurdat2_atlantic.txt"
ONI_FILE = DATA_RAW / "oni.txt"
JAMAICA_FILE = DATA_RAW / "jamaica_coastline.geojson"
BASEMAP_FILE = DATA_RAW / "caribbean_basemap.geojson"
IMPACTS_FILE = DATA_RAW / "jamaica_storm_impacts.csv"

# Geographic centre of Jamaica, used for bearings and map framing.
JAMAICA_CENTER = (18.1096, -77.2975)

# "Near Jamaica" means the track passed within this distance of the coastline.
NEAR_RADIUS_NM = 100
# Wider search window used when deciding which storms to keep at all.
SEARCH_RADIUS_NM = 600

# Data-quality eras. Satellite coverage begins in 1966; aircraft recon in 1944.
SATELLITE_ERA_START = 1966
MODERN_ERA_START = 1950

CATEGORY_ORDER = ["TD", "TS", "Cat 1", "Cat 2", "Cat 3", "Cat 4", "Cat 5"]
