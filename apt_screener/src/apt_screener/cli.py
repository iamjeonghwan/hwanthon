"""CLI: 네이버 매매 수집 → 통근 반영 → 투자 스크리닝."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from rich.console import Console
from rich.table import Table

from .commute import CommuteEstimator, load_subway_stations
from .hynix_shuttle import build_shuttle_dataset, save_shuttle_stops
from .naver_land import NaverLandClient, load_demo_listings
from .scoring import rank_listings

console = Console()
logger = logging.getLogger("apt_screener")

ROOT = Path(__file__).resolve().parents[2]


def _load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        example = ROOT / "config.example.yaml"
        console.print(f"[yellow]config 없음 → example 사용: {example}[/yellow]")
        path = example
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def cmd_fetch_shuttle(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    hs = cfg.get("hynix_shuttle", {})
    local = ROOT / hs.get("local_file", "data/hynix_shuttle_routes.json")
    user_csv = args.user_csv or hs.get("user_csv") or None
    if user_csv:
        user_csv = str(ROOT / user_csv) if not Path(user_csv).is_absolute() else user_csv

    stops, meta = build_shuttle_dataset(
        local_file=local,
        user_csv=user_csv,
        fetch_online=not args.offline,
    )
    out = Path(args.output) if args.output else local
    if not out.is_absolute():
        out = ROOT / out
    save_shuttle_stops(out, stops, destination=cfg.get("hynix_icheon"))
    console.print(f"[green]셔틀 정류장 {len(stops)}개 저장:[/green] {out}")
    console.print_json(json.dumps(meta, ensure_ascii=False))
    return 0


def cmd_screen(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    demo = args.demo or cfg.get("demo_mode", False)
    listings = []

    if demo:
        demo_path = ROOT / cfg.get("demo_data", "data/sample_complexes.json")
        console.print(f"[cyan]데모 모드:[/cyan] {demo_path}")
        listings = load_demo_listings(demo_path)
    else:
        delay = float(cfg.get("request_delay_sec", 1.0))
        with NaverLandClient(delay_sec=delay) as client:
            for region in cfg.get("regions", []):
                name = region.get("name", region["cortar_no"])
                cortar = str(region["cortar_no"])
                console.print(f"[cyan]수집 중:[/cyan] {name} ({cortar})")
                try:
                    part = client.fetch_region_listings(
                        cortar_no=cortar,
                        trade_type=cfg.get("trade_type", "A1"),
                        real_estate_type=cfg.get("real_estate_type", "APT"),
                        price_min=cfg.get("price_min_manwon"),
                        price_max=cfg.get("price_max_manwon"),
                        max_complexes=args.max_complexes,
                    )
                    console.print(f"  → 단지 {len(part)}개")
                    listings.extend(part)
                except Exception as exc:  # noqa: BLE001
                    console.print(f"[red]지역 수집 실패 {name}: {exc}[/red]")
                    console.print(
                        "[yellow]네이버 API가 차단/타임아웃이면 --demo 로 파이프라인 검증하세요.[/yellow]"
                    )

    if not listings:
        console.print("[red]매물이 없습니다.[/red]")
        return 1

    # 셔틀
    hs = cfg.get("hynix_shuttle", {})
    local = ROOT / hs.get("local_file", "data/hynix_shuttle_routes.json")
    user_csv = hs.get("user_csv") or None
    if user_csv and not Path(user_csv).is_absolute():
        user_csv = str(ROOT / user_csv)
    stops, shuttle_meta = build_shuttle_dataset(
        local_file=local,
        user_csv=user_csv,
        fetch_online=bool(hs.get("fetch_online", True)) and not args.offline,
    )
    console.print(
        f"셔틀 정류장 {shuttle_meta.get('final_count')}개 "
        f"(online hints={len(shuttle_meta.get('online_mentions') or [])})"
    )

    stations = load_subway_stations(ROOT / "data" / "subway_stations.json")
    estimator = CommuteEstimator(
        subway_stations=stations,
        shuttle_stops=stops,
        gangnam=cfg.get("gangnam_station", {"lat": 37.4979, "lon": 127.0276}),
        odsay_api_key=args.odsay_key or cfg.get("odsay_api_key") or "",
    )

    pairs = [(c, estimator.estimate(c)) for c in listings]
    ranked = rank_listings(pairs, weights=cfg.get("weights", {}))

    rows = [r.to_row() for r in ranked]
    df = pd.DataFrame(rows)

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "screen_results.csv"
    xlsx_path = out_dir / "screen_results.xlsx"
    json_path = out_dir / "screen_results.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    json_path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    table = Table(title="투자·통근 스크리닝 Top 결과")
    for col in [
        "rank_score",
        "complex_name",
        "min_price_manwon",
        "subway_walk_min",
        "gangnam_total_min",
        "hynix_total_min",
        "nearest_shuttle",
        "notes",
    ]:
        table.add_column(col, overflow="fold")
    for row in rows[: args.top]:
        table.add_row(*(str(row.get(c, "")) for c in [
            "rank_score",
            "complex_name",
            "min_price_manwon",
            "subway_walk_min",
            "gangnam_total_min",
            "hynix_total_min",
            "nearest_shuttle",
            "notes",
        ]))
    console.print(table)
    console.print(f"[green]저장:[/green] {csv_path}")
    console.print(f"[green]저장:[/green] {xlsx_path}")
    console.print(
        "[dim]면책: 투자 권유가 아닙니다. 셔틀 노선은 사내 공식 자료로 재확인하세요.[/dim]"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="네이버 아파트 매매 + 강남역/하이닉스 셔틀 통근 스크리너"
    )
    p.add_argument(
        "-c",
        "--config",
        default=str(ROOT / "config.yaml"),
        help="설정 YAML 경로",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("fetch-shuttle", help="하이닉스 셔틀 노선/정류장 데이터 갱신")
    s.add_argument("--user-csv", default=None, help="사내앱에서 정리한 정류장 CSV")
    s.add_argument("--output", default=None, help="저장 JSON 경로")
    s.add_argument("--offline", action="store_true", help="온라인 힌트 수집 생략")
    s.set_defaults(func=cmd_fetch_shuttle)

    s = sub.add_parser("screen", help="매물 수집 + 통근 스코어링")
    s.add_argument("--demo", action="store_true", help="샘플 데이터로 실행")
    s.add_argument("--offline", action="store_true", help="셔틀 온라인 힌트 생략")
    s.add_argument("--odsay-key", default="", help="ODsay API 키 (강남 통근 정밀화)")
    s.add_argument("--max-complexes", type=int, default=None, help="동별 최대 단지 수")
    s.add_argument("--top", type=int, default=15, help="콘솔 표시 상위 N")
    s.add_argument("--output-dir", default="output", help="결과 저장 폴더")
    s.set_defaults(func=cmd_screen)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = _load_config(Path(args.config))
    return int(args.func(cfg, args))


if __name__ == "__main__":
    sys.exit(main())
