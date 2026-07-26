from __future__ import annotations

from pathlib import Path

from apt_screener.commute import CommuteEstimator, load_subway_stations
from apt_screener.hynix_shuttle import load_shuttle_stops, merge_stops
from apt_screener.models import ShuttleStop
from apt_screener.naver_land import load_demo_listings, parse_price_manwon
from apt_screener.scoring import rank_listings
from apt_screener.service import run_screen

ROOT = Path(__file__).resolve().parents[1]


def test_parse_price():
    assert parse_price_manwon("17억 4,000") == 174000
    assert parse_price_manwon("9억") == 90000
    assert parse_price_manwon(82000) == 82000


def test_demo_pipeline_ranks_dual_commute_high():
    listings = load_demo_listings(ROOT / "data" / "sample_complexes.json")
    stops = load_shuttle_stops(ROOT / "data" / "hynix_shuttle_routes.json")
    stations = load_subway_stations(ROOT / "data" / "subway_stations.json")
    est = CommuteEstimator(
        subway_stations=stations,
        shuttle_stops=stops,
        gangnam={"lat": 37.4979, "lon": 127.0276},
    )
    pairs = [(c, est.estimate(c)) for c in listings]
    ranked = rank_listings(
        pairs,
        weights={
            "walk_to_subway": 0.2,
            "gangnam_commute": 0.3,
            "hynix_shuttle_commute": 0.3,
            "price_value": 0.1,
            "complex_quality": 0.1,
        },
    )
    assert ranked
    top_names = [r.complex.complex_name for r in ranked[:3]]
    # 성복/신정마을/판교가 이천 직주근접보다 듀얼 통근 점수가 높아야 함
    assert "이천현대성우2단지" not in top_names
    assert any("성복" in n or "신정" in n or "판교" in n for n in top_names)

    icheon = next(r for r in ranked if "이천" in r.complex.complex_name)
    seongbok = next(r for r in ranked if "성복" in r.complex.complex_name)
    assert seongbok.commute.gangnam_total_min < icheon.commute.gangnam_total_min


def test_merge_stops_prefers_user():
    a = [ShuttleStop("r", "성복역", 1.0, 2.0, 60, "seed")]
    b = [ShuttleStop("r", "성복역", 1.1, 2.1, 55, "user_csv")]
    merged = merge_stops(a, b)
    assert len(merged) == 1
    assert merged[0].ride_minutes_to_hynix == 55
    assert merged[0].source == "user_csv"


def test_run_screen_demo_payload():
    payload = run_screen(demo=True, offline=True)
    assert payload["mode"] == "demo"
    assert payload["results"]
    assert payload["shuttle_stops"]
    assert "lat" in payload["results"][0]
    assert "score_breakdown" in payload["results"][0]


def test_jangan_geonyeong_in_comparison():
    payload = run_screen(demo=True, offline=True)
    names = [r["complex_name"] for r in payload["results"]]
    assert "장안타운건영2차" in names
    item = next(r for r in payload["results"] if r["complex_name"] == "장안타운건영2차")
    assert item["watchlist"] is True
    assert item["lat"] and item["lon"]
    assert item["hynix_total_min"] < 90
    assert payload["meta"]["watchlist_count"] >= 1
