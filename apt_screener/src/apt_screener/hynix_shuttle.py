"""SK하이닉스 이천 통근 셔틀 노선/정류장 로더 + 온라인 힌트 수집."""

from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from .models import ShuttleStop

logger = logging.getLogger(__name__)

# 공개 웹에서 '노선/정류장' 언급을 찾기 위한 참고 URL 목록
# (공식 사내 노선표가 아님 — 힌트용. 실패해도 로컬 seed로 동작)
PUBLIC_HINT_URLS = [
    "https://huni-1017.tistory.com/280",
    "https://community.linkareer.com/mentor-sk/4333404",
]

# 공개 문서에서 자주 등장하는 정류장 키워드 → seed stop_name 매핑
KEYWORD_ALIASES = {
    "성복역": "성복역(신분당)",
    "수지구청역": "수지구청역(신분당)",
    "신정마을": "풍덕천 신정마을",
    "판교역": "판교역",
    "수내역": "수내역",
    "서현역": "서현역",
    "광교중앙": "광교중앙역",
    "영통역": "영통역",
    "동탄역": "동탄역",
    "미사": "미사강변도시",
    "대방역": "대방역",
    "구로디지털단지": "구로디지털단지역",
    "강남역": "강남역 인근",
    "잠실역": "잠실역 인근",
}


def load_shuttle_stops(path: str | Path) -> list[ShuttleStop]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    stops: list[ShuttleStop] = []
    for route in data.get("routes", []):
        route_name = str(route.get("route_name", ""))
        for s in route.get("stops", []):
            stops.append(
                ShuttleStop(
                    route_name=route_name,
                    stop_name=str(s["stop_name"]),
                    lat=float(s["lat"]),
                    lon=float(s["lon"]),
                    ride_minutes_to_hynix=float(s["ride_minutes_to_hynix"]),
                    source=str(s.get("source", "local")),
                )
            )
    return stops


def load_shuttle_csv(path: str | Path) -> list[ShuttleStop]:
    """사용자 CSV: route_name,stop_name,lat,lon,ride_minutes_to_hynix,source."""
    stops: list[ShuttleStop] = []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops.append(
                ShuttleStop(
                    route_name=row.get("route_name", "").strip(),
                    stop_name=row["stop_name"].strip(),
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                    ride_minutes_to_hynix=float(row["ride_minutes_to_hynix"]),
                    source=(row.get("source") or "user_csv").strip(),
                )
            )
    return stops


def save_shuttle_stops(
    path: str | Path,
    stops: list[ShuttleStop],
    destination: dict[str, Any] | None = None,
    preserve_notes: bool = True,
) -> None:
    by_route: dict[str, list[dict[str, Any]]] = {}
    for s in stops:
        by_route.setdefault(s.route_name or "기타", []).append(
            {
                "stop_name": s.stop_name,
                "lat": s.lat,
                "lon": s.lon,
                "ride_minutes_to_hynix": s.ride_minutes_to_hynix,
                "source": s.source,
            }
        )
    notes = [
        "공식 노선표는 임직원 전용(사내앱/인트라넷)이며 외부 공개가 제한됩니다.",
        "공개 커뮤니티·보도 기반 seed + online hint + user_csv merge 결과입니다.",
        "실제 이용 전 사내 노선표로 반드시 검증하세요.",
    ]
    path = Path(path)
    if preserve_notes and path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            if old.get("notes"):
                notes = list(old["notes"])
        except Exception:  # noqa: BLE001
            pass
    payload = {
        "updated_at": __import__("datetime").date.today().isoformat(),
        "destination": destination
        or {"name": "SK하이닉스 이천캠퍼스", "lat": 37.2450, "lon": 127.4780},
        "notes": notes,
        "routes": [
            {"route_name": name, "stops": items} for name, items in by_route.items()
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_online_route_hints(
    seed_stops: list[ShuttleStop],
    urls: list[str] | None = None,
    timeout: float = 20.0,
) -> tuple[list[ShuttleStop], list[dict[str, Any]]]:
    """공개 페이지에서 정류장 키워드를 스캔해 seed 정류장의 source를 보강.

    공식 PDF/좌표 API가 없으므로 '언급 여부'만 수집한다.
    새 좌표는 만들지 않고, 기존 seed와 매칭되는 정류장에 online_mention 태그를 붙인다.
    """
    urls = urls or PUBLIC_HINT_URLS
    mentions: list[dict[str, Any]] = []
    mentioned_names: set[str] = set()

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AptCommuteScreener/0.1; +local research)"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    with httpx.Client(headers=headers, timeout=timeout, follow_redirects=True) as client:
        for url in urls:
            try:
                r = client.get(url)
                if r.status_code != 200:
                    logger.warning("hint fetch status=%s url=%s", r.status_code, url)
                    continue
                text = re.sub(r"<[^>]+>", " ", r.text)
                text = re.sub(r"\s+", " ", text)
                found = []
                for key, canonical in KEYWORD_ALIASES.items():
                    if key in text:
                        found.append(canonical)
                        mentioned_names.add(canonical)
                mentions.append({"url": url, "matched_stops": found, "ok": True})
                logger.info("online hint %s → %s", url, found)
            except Exception as exc:  # noqa: BLE001
                mentions.append({"url": url, "matched_stops": [], "ok": False, "error": str(exc)})
                logger.warning("hint fetch failed %s: %s", url, exc)

    enriched: list[ShuttleStop] = []
    for s in seed_stops:
        source = s.source
        if s.stop_name in mentioned_names or any(
            s.stop_name.startswith(n.split("(")[0]) for n in mentioned_names
        ):
            source = f"{s.source}+online_mention" if "online" not in s.source else s.source
        enriched.append(
            ShuttleStop(
                route_name=s.route_name,
                stop_name=s.stop_name,
                lat=s.lat,
                lon=s.lon,
                ride_minutes_to_hynix=s.ride_minutes_to_hynix,
                source=source,
            )
        )
    return enriched, mentions


def merge_stops(*groups: list[ShuttleStop]) -> list[ShuttleStop]:
    """stop_name+route 기준으로 뒤 그룹이 앞을 덮어씀."""
    merged: dict[tuple[str, str], ShuttleStop] = {}
    for group in groups:
        for s in group:
            merged[(s.route_name, s.stop_name)] = s
    return list(merged.values())


def build_shuttle_dataset(
    local_file: str | Path,
    user_csv: str | Path | None = None,
    fetch_online: bool = True,
) -> tuple[list[ShuttleStop], dict[str, Any]]:
    seed = load_shuttle_stops(local_file)
    meta: dict[str, Any] = {"seed_count": len(seed), "online_mentions": []}

    online: list[ShuttleStop] = []
    if fetch_online:
        online, mentions = fetch_online_route_hints(seed)
        meta["online_mentions"] = mentions
    else:
        online = seed

    user: list[ShuttleStop] = []
    if user_csv and Path(user_csv).exists():
        user = load_shuttle_csv(user_csv)
        meta["user_csv_count"] = len(user)

    stops = merge_stops(seed, online, user)
    meta["final_count"] = len(stops)
    return stops, meta
