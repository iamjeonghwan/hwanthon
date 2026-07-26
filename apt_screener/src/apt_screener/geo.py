"""거리·도보시간 유틸."""

from __future__ import annotations

import math
from typing import Iterable, TypeVar

T = TypeVar("T")

# 평지 평균 보행 속도 (m/min) — 약 4.5km/h
WALK_SPEED_M_PER_MIN = 75.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 좌표 사이 직선거리(미터)."""
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def walk_minutes(distance_m: float, factor: float = 1.25) -> float:
    """직선거리 → 도보 분. factor로 도로 우회를 보정."""
    return (distance_m * factor) / WALK_SPEED_M_PER_MIN


def nearest(
    lat: float,
    lon: float,
    items: Iterable[T],
    lat_key: str = "lat",
    lon_key: str = "lon",
) -> tuple[T | None, float]:
    """가장 가까운 항목과 거리(m)."""
    best: T | None = None
    best_d = float("inf")
    for item in items:
        if isinstance(item, dict):
            ilat, ilon = float(item[lat_key]), float(item[lon_key])
        else:
            ilat, ilon = float(getattr(item, lat_key)), float(getattr(item, lon_key))
        d = haversine_m(lat, lon, ilat, ilon)
        if d < best_d:
            best, best_d = item, d
    return best, best_d
