"""투자·통근 관점 스코어링."""

from __future__ import annotations

from .models import CommuteProfile, ComplexListing, ScoredApartment


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _inv_time_score(minutes: float, good: float, bad: float) -> float:
    """짧을수록 높은 점수. good 이하=1, bad 이상=0."""
    if minutes <= good:
        return 1.0
    if minutes >= bad:
        return 0.0
    return 1.0 - (minutes - good) / (bad - good)


def score_apartment(
    complex_: ComplexListing,
    commute: CommuteProfile,
    weights: dict[str, float],
    ref_price_per_pyeong: float | None = None,
) -> ScoredApartment:
    walk_sub = _inv_time_score(commute.subway_walk_min, good=5, bad=20)
    gangnam = _inv_time_score(commute.gangnam_total_min, good=25, bad=75)
    hynix = _inv_time_score(commute.hynix_total_min, good=50, bad=120)

    # 가격: 같은 배치 중앙값 대비 저렴할수록 가점 (투기 추천 아님, 상대 가치)
    ppp = complex_.median_price_per_pyeong
    if ppp and ref_price_per_pyeong and ref_price_per_pyeong > 0:
        ratio = ppp / ref_price_per_pyeong
        price_value = _clamp01(1.3 - ratio)  # 중앙값보다 30% 싸면 만점권
    else:
        price_value = 0.5

    # 단지 품질 프록시: 세대수(유동성) + 연식 페널티 완화(리모델링/신축 가점)
    hh = complex_.household_count or 0
    liquidity = _clamp01(hh / 1500)
    age = complex_.building_age_years
    if age is None:
        age_score = 0.5
    elif age <= 5:
        age_score = 1.0
    elif age <= 15:
        age_score = 0.8
    elif age <= 25:
        age_score = 0.55
    else:
        age_score = 0.35
    complex_quality = 0.6 * liquidity + 0.4 * age_score

    breakdown = {
        "walk_to_subway": walk_sub,
        "gangnam_commute": gangnam,
        "hynix_shuttle_commute": hynix,
        "price_value": price_value,
        "complex_quality": complex_quality,
    }
    total = 0.0
    wsum = 0.0
    for k, v in breakdown.items():
        w = float(weights.get(k, 0.0))
        total += w * v
        wsum += w
    score = 100.0 * (total / wsum if wsum else 0.0)

    notes: list[str] = []
    if commute.subway_walk_min <= 7:
        notes.append("초역세권(도보≤7분)")
    if commute.gangnam_total_min <= 35:
        notes.append("강남 지하철 출근 유리")
    if commute.shuttle_walk_min <= 10 and commute.hynix_total_min <= 70:
        notes.append("하이닉스 셔틀 접근 우수")
    if commute.gangnam_total_min <= 40 and commute.hynix_total_min <= 75:
        notes.append("맞벌이(강남+하이닉스) 듀얼 통근 적합")
    if hh >= 1000:
        notes.append("대단지 유동성")
    if age is not None and age >= 25 and commute.subway_walk_min <= 8:
        notes.append("구축·역세권(리모델링/재건축 테마 관찰)")
    if "이천" in complex_.address and commute.hynix_total_min < 30:
        notes.append("이천 직주근접 — 생활권/학군 별도 검증 필요")

    return ScoredApartment(
        complex=complex_,
        commute=commute,
        score=score,
        score_breakdown=breakdown,
        investment_notes=notes,
    )


def rank_listings(
    pairs: list[tuple[ComplexListing, CommuteProfile]],
    weights: dict[str, float],
) -> list[ScoredApartment]:
    ppps = [
        c.median_price_per_pyeong
        for c, _ in pairs
        if c.median_price_per_pyeong
    ]
    ref = None
    if ppps:
        ppps = sorted(ppps)
        ref = ppps[len(ppps) // 2]

    scored = [score_apartment(c, q, weights, ref_price_per_pyeong=ref) for c, q in pairs]
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored
