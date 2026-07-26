"""데이터 모델."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Article:
    article_no: str
    price_text: str
    price_manwon: int
    exclusive_area_m2: float
    supply_area_m2: float | None = None
    floor_info: str = ""
    direction: str = ""
    confirm_ymd: str = ""

    @property
    def price_per_pyeong(self) -> float | None:
        if self.exclusive_area_m2 <= 0:
            return None
        pyeong = self.exclusive_area_m2 / 3.3058
        return self.price_manwon / pyeong


@dataclass
class ComplexListing:
    complex_no: str
    complex_name: str
    address: str
    lat: float
    lon: float
    household_count: int = 0
    use_approve_ymd: str = ""
    articles: list[Article] = field(default_factory=list)
    deal_count: int = 0
    watchlist: bool = False

    @property
    def min_price_manwon(self) -> int | None:
        if not self.articles:
            return None
        return min(a.price_manwon for a in self.articles)

    @property
    def median_price_per_pyeong(self) -> float | None:
        vals = [a.price_per_pyeong for a in self.articles if a.price_per_pyeong]
        if not vals:
            return None
        vals = sorted(vals)
        mid = len(vals) // 2
        if len(vals) % 2:
            return vals[mid]
        return (vals[mid - 1] + vals[mid]) / 2

    @property
    def building_age_years(self) -> int | None:
        if not self.use_approve_ymd or len(self.use_approve_ymd) < 4:
            return None
        try:
            year = int(self.use_approve_ymd[:4])
            return max(0, 2026 - year)
        except ValueError:
            return None


@dataclass
class ShuttleStop:
    route_name: str
    stop_name: str
    lat: float
    lon: float
    ride_minutes_to_hynix: float
    source: str = "local"


@dataclass
class CommuteProfile:
    nearest_subway: str
    subway_walk_min: float
    gangnam_subway_min: float
    gangnam_total_min: float
    nearest_shuttle_stop: str
    nearest_shuttle_route: str
    shuttle_walk_min: float
    shuttle_ride_min: float
    hynix_total_min: float
    gangnam_source: str
    hynix_source: str


@dataclass
class ScoredApartment:
    complex: ComplexListing
    commute: CommuteProfile
    score: float
    score_breakdown: dict[str, float]
    investment_notes: list[str] = field(default_factory=list)

    def to_row(self) -> dict[str, Any]:
        c = self.complex
        q = self.commute
        return {
            "rank_score": round(self.score, 2),
            "complex_name": c.complex_name,
            "address": c.address,
            "complex_no": c.complex_no,
            "watchlist": c.watchlist,
            "min_price_manwon": c.min_price_manwon,
            "median_manwon_per_pyeong": (
                round(c.median_price_per_pyeong, 1) if c.median_price_per_pyeong else None
            ),
            "households": c.household_count,
            "building_age_years": c.building_age_years,
            "listing_count": len(c.articles),
            "nearest_subway": q.nearest_subway,
            "subway_walk_min": round(q.subway_walk_min, 1),
            "gangnam_total_min": round(q.gangnam_total_min, 1),
            "nearest_shuttle": q.nearest_shuttle_stop,
            "shuttle_route": q.nearest_shuttle_route,
            "shuttle_walk_min": round(q.shuttle_walk_min, 1),
            "hynix_total_min": round(q.hynix_total_min, 1),
            "notes": " | ".join(self.investment_notes),
            "lat": c.lat,
            "lon": c.lon,
            **{f"score_{k}": round(v, 2) for k, v in self.score_breakdown.items()},
        }

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
