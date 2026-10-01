"""Página estática honesta em `/`. Sem CDN, sem fonte remota, sem botão falso.

CSS e JS ficam em arquivos próprios (`/static/...`) porque a CSP `default-src 'self'`
não permite estilo nem script inline.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter(tags=["ui"])

STATIC_DIR: Path = Path(__file__).resolve().parent.parent / "static"
INDEX_HTML: Path = STATIC_DIR / "index.html"


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Estado do Edge e lista de equipamentos."""
    return FileResponse(
        INDEX_HTML,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-cache"},
    )
