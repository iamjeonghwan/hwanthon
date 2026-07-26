"""CLI·웹 공용 스크리닝 서비스."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from .commute import CommuteEstimator, load_subway_stations
from .hynix_shuttle import build_shuttle_dataset, load_shuttle_stops
from .models import ComplexListing, ScoredApartment
from .naver_land import NaverLandClient, load_demo_listings, load_watchlist_listings
from .scoring import rank_listings

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    path = Path(path) if path else ROOT / "config.yaml"
    if not path.exists():
        path = ROOT / "config.example.yaml"
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _merge_listings(
    base: list[ComplexListing], extra: list[ComplexListing]
) -> list[ComplexListing]:
    by_no = {c.complex_no: c for c in base}
    for item in extra:
        existing = by_no.get(item.complex_no)
        if existing is None:
            by_no[item.complex_no] = item
        else:
            existing.watchlist = existing.watchlist or item.watchlist
    # name fallback for watchlist highlight
    watch_names = {c.complex_name for c in extra if c.watchlist}
    for c in by_no.values():
        if c.complex_name in watch_names:
            c.watchlist = True
    return list(by_no.values())


def _watchlist_from_config(cfg: dict[str, Any]) -> list[ComplexListing]:
    wl = cfg.get("watchlist") or {}
    demo_path = ROOT / cfg.get("demo_data", "data/sample_complexes.json")
    names = list(wl.get("complex_names") or [])
    nos = [str(x) for x in (wl.get("complex_nos") or [])]
    # seed 파일의 watchlist:true + config 지정 단지
    return load_watchlist_listings(demo_path, names=names, complex_nos=nos)


def run_screen(
    cfg: dict[str, Any] | None = None,
    *,
    demo: bool = True,
    offline: bool = True,
    odsay_api_key: str = "",
    max_complexes: int | None = None,
) -> dict[str, Any]:
    """스크리닝 실행 후 웹/API용 페이로드 반환."""
    cfg = cfg or load_config()
    listings: list[ComplexListing] = []
    errors: list[str] = []
    watchlist = _watchlist_from_config(cfg)

    if demo:
        demo_path = ROOT / cfg.get("demo_data", "data/sample_complexes.json")
        listings = load_demo_listings(demo_path)
        mode = "demo"
    else:
        mode = "live"
        delay = float(cfg.get("request_delay_sec", 1.0))
        with NaverLandClient(delay_sec=delay) as client:
            for region in cfg.get("regions", []):
                name = region.get("name", region["cortar_no"])
                cortar = str(region["cortar_no"])
                try:
                    part = client.fetch_region_listings(
                        cortar_no=cortar,
                        trade_type=cfg.get("trade_type", "A1"),
                        real_estate_type=cfg.get("real_estate_type", "APT"),
                        price_min=cfg.get("price_min_manwon"),
                        price_max=cfg.get("price_max_manwon"),
                        max_complexes=max_complexes,
                    )
                    listings.extend(part)
                except Exception as exc:  # noqa: BLE001
                    msg = f"{name}: {exc}"
                    errors.append(msg)
                    logger.warning("region fetch failed: %s", msg)

    # 워치리스트(장안타운건영2차 등)는 항상 결과에 포함해 비교
    listings = _merge_listings(listings, watchlist)

    hs = cfg.get("hynix_shuttle", {})
    local = ROOT / hs.get("local_file", "data/hynix_shuttle_routes.json")
    user_csv = hs.get("user_csv") or None
    if user_csv and not Path(str(user_csv)).is_absolute():
        user_csv = str(ROOT / user_csv)

    stops, shuttle_meta = build_shuttle_dataset(
        local_file=local,
        user_csv=user_csv,
        fetch_online=bool(hs.get("fetch_online", True)) and not offline,
    )
    if not stops:
        stops = load_shuttle_stops(local)

    stations = load_subway_stations(ROOT / "data" / "subway_stations.json")
    gangnam = cfg.get("gangnam_station", {"name": "강남역", "lat": 37.4979, "lon": 127.0276})
    hynix = cfg.get("hynix_icheon", {"name": "SK하이닉스 이천", "lat": 37.2450, "lon": 127.4780})

    estimator = CommuteEstimator(
        subway_stations=stations,
        shuttle_stops=stops,
        gangnam=gangnam,
        odsay_api_key=odsay_api_key or cfg.get("odsay_api_key") or "",
    )

    pairs = [(c, estimator.estimate(c)) for c in listings]
    ranked = rank_listings(pairs, weights=cfg.get("weights", {}))

    return {
        "mode": mode,
        "errors": errors,
        "meta": {
            "listing_count": len(listings),
            "ranked_count": len(ranked),
            "watchlist_count": sum(1 for c in listings if c.watchlist),
            "shuttle": shuttle_meta,
            "weights": cfg.get("weights", {}),
        },
        "anchors": {
            "gangnam": gangnam,
            "hynix": hynix,
        },
        "shuttle_stops": [
            {
                "route_name": s.route_name,
                "stop_name": s.stop_name,
                "lat": s.lat,
                "lon": s.lon,
                "ride_minutes_to_hynix": s.ride_minutes_to_hynix,
                "source": s.source,
            }
            for s in stops
        ],
        "subway_stations": stations,
        "results": [_detail(r, i + 1) for i, r in enumerate(ranked)],
    }


def _detail(item: ScoredApartment, rank: int) -> dict[str, Any]:
    c = item.complex
    q = item.commute
    row = item.to_row()
    row["rank"] = rank
    row["articles"] = [
        {
            "article_no": a.article_no,
            "price_text": a.price_text,
            "price_manwon": a.price_manwon,
            "exclusive_area_m2": a.exclusive_area_m2,
            "floor_info": a.floor_info,
            "direction": a.direction,
            "price_per_pyeong": round(a.price_per_pyeong, 1) if a.price_per_pyeong else None,
        }
        for a in c.articles
    ]
    row["score_breakdown"] = {k: round(v, 3) for k, v in item.score_breakdown.items()}
    row["commute"] = {
        "nearest_subway": q.nearest_subway,
        "subway_walk_min": round(q.subway_walk_min, 1),
        "gangnam_subway_min": round(q.gangnam_subway_min, 1),
        "gangnam_total_min": round(q.gangnam_total_min, 1),
        "nearest_shuttle_stop": q.nearest_shuttle_stop,
        "nearest_shuttle_route": q.nearest_shuttle_route,
        "shuttle_walk_min": round(q.shuttle_walk_min, 1),
        "shuttle_ride_min": round(q.shuttle_ride_min, 1),
        "hynix_total_min": round(q.hynix_total_min, 1),
        "gangnam_source": q.gangnam_source,
        "hynix_source": q.hynix_source,
    }
    row["investment_notes"] = item.investment_notes
    return row
