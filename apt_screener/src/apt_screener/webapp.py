"""FastAPI 웹 UI — 지도·랭킹 시각화."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .service import load_config, run_screen

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "web" / "static"

app = FastAPI(title="통근맵", description="아파트 매매 · 강남/하이닉스 통근 스크리너")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_cache: dict[str, Any] = {}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/screen")
def api_screen(
    demo: bool = Query(True, description="샘플 데이터 사용"),
    offline: bool = Query(True, description="셔틀 온라인 힌트 생략"),
    refresh: bool = Query(False, description="캐시 무시"),
    max_complexes: int | None = Query(None, ge=1, le=50),
) -> dict[str, Any]:
    key = f"{demo}:{offline}:{max_complexes}"
    if not refresh and key in _cache:
        payload = dict(_cache[key])
        payload["cached"] = True
        return payload

    cfg = load_config()
    payload = run_screen(
        cfg,
        demo=demo,
        offline=offline,
        max_complexes=max_complexes,
    )
    _cache[key] = payload
    out = dict(payload)
    out["cached"] = False
    return out


def create_app() -> FastAPI:
    return app
