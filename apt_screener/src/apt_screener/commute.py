"""지하철·강남·하이닉스 셔틀 통근시간 산출."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from .geo import nearest, walk_minutes
from .models import CommuteProfile, ComplexListing, ShuttleStop

logger = logging.getLogger(__name__)


def load_subway_stations(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("stations", []))


class CommuteEstimator:
    def __init__(
        self,
        subway_stations: list[dict[str, Any]],
        shuttle_stops: list[ShuttleStop],
        gangnam: dict[str, float],
        odsay_api_key: str = "",
    ) -> None:
        self.subway_stations = subway_stations
        self.shuttle_stops = shuttle_stops
        self.gangnam = gangnam
        self.odsay_api_key = odsay_api_key.strip()

    def estimate(self, complex_: ComplexListing) -> CommuteProfile:
        # 직선 2.5km(도보 약 40분+) 밖 역은 비역세로 간주
        subway, subway_dist = nearest(complex_.lat, complex_.lon, self.subway_stations)
        if subway is None or subway_dist > 2500:
            subway_name, subway_walk, table_gangnam = "N/A(원거리)", 999.0, 999.0
        else:
            subway_walk = walk_minutes(subway_dist)
            subway_name = str(subway["name"])
            table_gangnam = float(subway["to_gangnam_min"])

        gangnam_source = "station_table"
        gangnam_ride = table_gangnam
        if self.odsay_api_key:
            odsay = self._odsay_minutes(
                complex_.lat,
                complex_.lon,
                float(self.gangnam["lat"]),
                float(self.gangnam["lon"]),
            )
            if odsay is not None:
                # ODsay는 도보 포함 총시간 → 역 도보와 분리하지 않고 총시간으로 사용
                gangnam_source = "odsay"
                return self._with_shuttle(
                    complex_,
                    subway_name=subway_name,
                    subway_walk=subway_walk,
                    gangnam_ride=max(0.0, odsay - subway_walk),
                    gangnam_total=odsay,
                    gangnam_source=gangnam_source,
                )

        gangnam_total = subway_walk + gangnam_ride
        return self._with_shuttle(
            complex_,
            subway_name=subway_name,
            subway_walk=subway_walk,
            gangnam_ride=gangnam_ride,
            gangnam_total=gangnam_total,
            gangnam_source=gangnam_source,
        )

    def _with_shuttle(
        self,
        complex_: ComplexListing,
        *,
        subway_name: str,
        subway_walk: float,
        gangnam_ride: float,
        gangnam_total: float,
        gangnam_source: str,
    ) -> CommuteProfile:
        stop, stop_dist = nearest(complex_.lat, complex_.lon, self.shuttle_stops)
        if stop is None:
            return CommuteProfile(
                nearest_subway=subway_name,
                subway_walk_min=subway_walk,
                gangnam_subway_min=gangnam_ride,
                gangnam_total_min=gangnam_total,
                nearest_shuttle_stop="N/A",
                nearest_shuttle_route="",
                shuttle_walk_min=999.0,
                shuttle_ride_min=999.0,
                hynix_total_min=999.0,
                gangnam_source=gangnam_source,
                hynix_source="none",
            )

        shuttle_walk = walk_minutes(stop_dist)
        hynix_total = shuttle_walk + stop.ride_minutes_to_hynix
        return CommuteProfile(
            nearest_subway=subway_name,
            subway_walk_min=subway_walk,
            gangnam_subway_min=gangnam_ride,
            gangnam_total_min=gangnam_total,
            nearest_shuttle_stop=stop.stop_name,
            nearest_shuttle_route=stop.route_name,
            shuttle_walk_min=shuttle_walk,
            shuttle_ride_min=stop.ride_minutes_to_hynix,
            hynix_total_min=hynix_total,
            gangnam_source=gangnam_source,
            hynix_source=stop.source,
        )

    def _odsay_minutes(self, sy: float, sx: float, ey: float, ex: float) -> float | None:
        """ODsay 대중교통 소요시간(분). API 키 필요."""
        url = "https://api.odsay.com/v1/api/searchPubTransPathT"
        params = {
            "SX": sx,
            "SY": sy,
            "EX": ex,
            "EY": ey,
            "apiKey": self.odsay_api_key,
        }
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
            if "error" in data:
                logger.warning("odsay error: %s", data["error"])
                return None
            paths = data.get("result", {}).get("path") or []
            if not paths:
                return None
            # 최단시간
            best = min(paths, key=lambda p: p.get("info", {}).get("totalTime", 10**9))
            return float(best["info"]["totalTime"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("odsay failed: %s", exc)
            return None
