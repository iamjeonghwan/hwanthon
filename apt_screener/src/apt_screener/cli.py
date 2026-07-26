"""CLI: 네이버 매매 수집 → 통근 반영 → 투자 스크리닝."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.table import Table

from .hynix_shuttle import build_shuttle_dataset, save_shuttle_stops
from .service import ROOT, load_config, run_screen

console = Console()
logger = logging.getLogger("apt_screener")


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
    payload = run_screen(
        cfg,
        demo=args.demo or cfg.get("demo_mode", False),
        offline=args.offline,
        odsay_api_key=args.odsay_key or "",
        max_complexes=args.max_complexes,
    )
    rows = payload["results"]
    if not rows:
        console.print("[red]매물이 없습니다.[/red]")
        for err in payload.get("errors") or []:
            console.print(f"[yellow]{err}[/yellow]")
        return 1

    df = pd.DataFrame([{k: v for k, v in r.items() if k not in {"articles", "score_breakdown", "commute", "investment_notes"}} for r in rows])
    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "screen_results.csv"
    xlsx_path = out_dir / "screen_results.xlsx"
    json_path = out_dir / "screen_results.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    table = Table(title="투자·통근 스크리닝 Top 결과")
    cols = [
        "rank_score",
        "complex_name",
        "min_price_manwon",
        "subway_walk_min",
        "gangnam_total_min",
        "hynix_total_min",
        "nearest_shuttle",
        "notes",
    ]
    for col in cols:
        table.add_column(col, overflow="fold")
    for row in rows[: args.top]:
        table.add_row(*(str(row.get(c, "")) for c in cols))
    console.print(table)
    console.print(f"[green]저장:[/green] {csv_path}")
    console.print(f"[green]저장:[/green] {xlsx_path}")
    console.print(
        "[dim]면책: 투자 권유가 아닙니다. 셔틀 노선은 사내 공식 자료로 재확인하세요.[/dim]"
    )
    return 0


def cmd_web(cfg: dict[str, Any], args: argparse.Namespace) -> int:
    import uvicorn

    console.print(f"[cyan]웹 UI:[/cyan] http://{args.host}:{args.port}")
    uvicorn.run(
        "apt_screener.webapp:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
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

    s = sub.add_parser("web", help="시각화 웹 UI 실행")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_web)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    cfg = load_config(Path(args.config))
    return int(args.func(cfg, args))


if __name__ == "__main__":
    sys.exit(main())
