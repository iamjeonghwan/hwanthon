"""네이버 부동산(new.land.naver.com) 매매 매물 수집."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx

from .models import Article, ComplexListing

logger = logging.getLogger(__name__)

NEW_LAND = "https://new.land.naver.com"
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://new.land.naver.com/complexes",
}


def parse_price_manwon(text: str | int | float | None) -> int | None:
    """'17억 4,000' / '9억' / 174000 → 만원 단위 int."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip().replace(",", "").replace(" ", "")
    if not s:
        return None
    if s.isdigit():
        return int(s)
    eok = 0
    man = 0
    m_eok = re.search(r"(\d+)억", s)
    if m_eok:
        eok = int(m_eok.group(1))
    m_man = re.search(r"억\s*(\d+)", str(text).replace(",", ""))
    if m_man:
        man = int(m_man.group(1))
    elif "억" not in s:
        m_only = re.search(r"(\d+)", s)
        if m_only:
            return int(m_only.group(1))
    return eok * 10000 + man


class NaverLandClient:
    def __init__(self, delay_sec: float = 1.0, timeout: float = 30.0) -> None:
        self.delay_sec = delay_sec
        self._client = httpx.Client(
            headers=DEFAULT_HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )
        self._last_call = 0.0

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NaverLandClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.delay_sec:
            time.sleep(self.delay_sec - elapsed)
        self._last_call = time.time()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = path if path.startswith("http") else f"{NEW_LAND}{path}"
        for attempt in range(3):
            self._throttle()
            try:
                r = self._client.get(url, params=params)
            except httpx.TimeoutException:
                logger.warning("timeout %s (attempt %s)", url, attempt + 1)
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"네이버 부동산 요청 실패: {url}")

    def list_regions(self, cortar_no: str) -> list[dict[str, Any]]:
        data = self._get("/api/regions/list", {"cortarNo": cortar_no})
        return data.get("regionList") or data.get("regions") or []

    def list_complexes(self, cortar_no: str, real_estate_type: str = "APT") -> list[dict[str, Any]]:
        data = self._get(
            "/api/regions/complexes",
            {"cortarNo": cortar_no, "realEstateType": real_estate_type, "order": ""},
        )
        if isinstance(data, list):
            return data
        return data.get("complexList") or data.get("list") or []

    def complex_detail(self, complex_no: str) -> dict[str, Any]:
        data = self._get(f"/api/complexes/{complex_no}")
        if isinstance(data, dict) and "complexDetail" in data:
            return data["complexDetail"]
        return data if isinstance(data, dict) else {}

    def list_articles(
        self,
        complex_no: str,
        trade_type: str = "A1",
        real_estate_type: str = "APT",
        max_pages: int = 20,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            data = self._get(
                f"/api/articles/complex/{complex_no}",
                {
                    "realEstateType": real_estate_type,
                    "tradeType": trade_type,
                    "page": page,
                    "complexNo": complex_no,
                    "order": "rank",
                },
            )
            articles = data.get("articleList") or []
            if not articles:
                break
            results.extend(articles)
            if not data.get("isMoreData"):
                break
        return results

    def fetch_region_listings(
        self,
        cortar_no: str,
        trade_type: str = "A1",
        real_estate_type: str = "APT",
        price_min: int | None = None,
        price_max: int | None = None,
        max_complexes: int | None = None,
    ) -> list[ComplexListing]:
        raw_complexes = self.list_complexes(cortar_no, real_estate_type=real_estate_type)
        if max_complexes:
            raw_complexes = raw_complexes[:max_complexes]

        out: list[ComplexListing] = []
        for raw in raw_complexes:
            cno = str(raw.get("complexNo") or raw.get("hscpNo") or "")
            if not cno:
                continue
            detail = {}
            try:
                detail = self.complex_detail(cno)
            except Exception as exc:  # noqa: BLE001
                logger.debug("complex detail skip %s: %s", cno, exc)

            lat = float(detail.get("latitude") or raw.get("latitude") or raw.get("lat") or 0)
            lon = float(detail.get("longitude") or raw.get("longitude") or raw.get("lon") or 0)
            if not lat or not lon:
                logger.warning("좌표 없음, skip complex %s", cno)
                continue

            articles_raw = self.list_articles(
                cno, trade_type=trade_type, real_estate_type=real_estate_type
            )
            articles: list[Article] = []
            for a in articles_raw:
                price_text = str(a.get("dealOrWarrantPrc") or a.get("prcInfo") or "")
                price = parse_price_manwon(price_text) or parse_price_manwon(a.get("dealPrice"))
                if price is None:
                    continue
                if price_min is not None and price < price_min:
                    continue
                if price_max is not None and price > price_max:
                    continue
                area1 = float(a.get("area1") or a.get("spc1") or 0)
                area2 = a.get("area2") or a.get("spc2")
                articles.append(
                    Article(
                        article_no=str(a.get("articleNo") or a.get("atclNo") or ""),
                        price_text=price_text,
                        price_manwon=price,
                        exclusive_area_m2=area1,
                        supply_area_m2=float(area2) if area2 else None,
                        floor_info=str(a.get("floorInfo") or a.get("flrInfo") or ""),
                        direction=str(a.get("direction") or ""),
                        confirm_ymd=str(a.get("articleConfirmYmd") or ""),
                    )
                )

            if not articles:
                continue

            out.append(
                ComplexListing(
                    complex_no=cno,
                    complex_name=str(
                        detail.get("complexName")
                        or raw.get("complexName")
                        or raw.get("hscpNm")
                        or cno
                    ),
                    address=str(
                        detail.get("cortarAddress")
                        or raw.get("cortarAddress")
                        or raw.get("address")
                        or ""
                    ),
                    lat=lat,
                    lon=lon,
                    household_count=int(
                        detail.get("totalHouseholdCount")
                        or raw.get("totalHouseholdCount")
                        or 0
                    ),
                    use_approve_ymd=str(
                        detail.get("useApproveYmd") or raw.get("useApproveYmd") or ""
                    ),
                    articles=articles,
                    deal_count=int(raw.get("dealCount") or len(articles)),
                )
            )
        return out


def load_demo_listings(path: str | Path) -> list[ComplexListing]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    out: list[ComplexListing] = []
    for raw in data.get("complexes", []):
        articles = [
            Article(
                article_no=str(a.get("articleNo", "")),
                price_text=str(a.get("dealOrWarrantPrc", "")),
                price_manwon=int(a["priceManwon"]),
                exclusive_area_m2=float(a.get("area1") or 0),
                supply_area_m2=float(a["area2"]) if a.get("area2") else None,
                floor_info=str(a.get("floorInfo", "")),
                direction=str(a.get("direction", "")),
                confirm_ymd=str(a.get("articleConfirmYmd", "")),
            )
            for a in raw.get("articles", [])
        ]
        out.append(
            ComplexListing(
                complex_no=str(raw["complexNo"]),
                complex_name=str(raw["complexName"]),
                address=str(raw.get("cortarAddress", "")),
                lat=float(raw["latitude"]),
                lon=float(raw["longitude"]),
                household_count=int(raw.get("totalHouseholdCount") or 0),
                use_approve_ymd=str(raw.get("useApproveYmd") or ""),
                articles=articles,
                deal_count=int(raw.get("dealCount") or len(articles)),
            )
        )
    return out
