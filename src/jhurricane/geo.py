"""Geometry helpers: distance to the Jamaican coastline, bearings, compass labels."""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import shapely
from shapely.geometry import shape
from sklearn.neighbors import BallTree

from . import config

EARTH_RADIUS_NM = 3440.065


def haversine_nm(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_NM * np.arcsin(np.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    x = np.sin(lon2 - lon1) * np.cos(lat2)
    y = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(lon2 - lon1)
    return (np.degrees(np.arctan2(x, y)) + 360) % 360


def compass(bearing):
    labels = np.array(["N", "NE", "E", "SE", "S", "SW", "W", "NW"])
    return labels[((np.asarray(bearing) + 22.5) // 45).astype(int) % 8]


@lru_cache(maxsize=1)
def jamaica_polygon():
    with open(config.JAMAICA_FILE, encoding="utf-8") as fh:
        return shape(json.load(fh)["features"][0]["geometry"])


@lru_cache(maxsize=1)
def _coast_tree():
    # Densify the coastline to ~0.5 km spacing, then index it for fast nearest-point lookup.
    boundary = shapely.segmentize(jamaica_polygon().boundary, 0.005)
    coords = shapely.get_coordinates(boundary)  # (lon, lat)
    return BallTree(np.radians(coords[:, ::-1]), metric="haversine")


def distance_to_coast_nm(lat, lon):
    """Great-circle distance (nm) from each point to the Jamaican coast; 0 if over land."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    dist, _ = _coast_tree().query(np.radians(np.column_stack([lat, lon])), k=1)
    dist = dist[:, 0] * EARTH_RADIUS_NM
    over_land = shapely.contains_xy(jamaica_polygon(), lon, lat)
    return np.where(over_land, 0.0, dist)
