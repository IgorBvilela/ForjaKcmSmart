"""Interface local: o app Svelte compilado em `/app/*` e a página estática honesta como reserva.

Com o build em `src/forja/ui/dist` (gerado por `scripts/build_ui.ps1`):
- `/app/<arquivo existente>` serve o arquivo. Assets com hash (`/app/assets/*`) são imutáveis
  (cache de um ano); o resto (`index.html`, `brand/*`, `licenses/*`) sai com `no-cache`.
- Qualquer outro caminho sob `/app` cai no `index.html` (roteador do lado do cliente).
- `/` entrega o mesmo `index.html` (200) e o roteador normaliza a URL para `/app/plant`.
  Não é redirect HTTP de propósito: o contrato de `/` exige `200 text/html` com "Somente leitura"
  no corpo (`tests/integration/test_api_security_headers.py`), e o index do app cumpre isso.

Sem o build, `/` mostra a página estática de `src/forja/api/static` e `/app/*` responde 404 com
envelope e instrução de build. CSS e JS nunca são inline: a CSP é `default-src 'self'`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from fastapi import APIRouter
from fastapi.responses import FileResponse

from forja.api.errors import ApiError

router = APIRouter(tags=["ui"])

STATIC_DIR: Path = Path(__file__).resolve().parent.parent / "static"
INDEX_HTML: Path = STATIC_DIR / "index.html"

UI_DIST: Path = Path(__file__).resolve().parents[2] / "ui" / "dist"
"""`src/forja/ui/dist`: saída do `vite build` (gitignored)."""
UI_INDEX: Path = UI_DIST / "index.html"
UI_ASSETS_PREFIX: Final = "assets/"

CACHE_IMMUTABLE: Final = "public, max-age=31536000, immutable"
CACHE_NO_CACHE: Final = "no-cache"

# Tipos explícitos: no Windows, `mimetypes` pode devolver `text/plain` para `.js` conforme o
# registro, e módulo ES com tipo errado é bloqueado pelo navegador.
MEDIA_TYPES: Final[dict[str, str]] = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json",
}

UI_NOT_BUILT_PT: Final = (
    "Interface não compilada neste Edge. Rode scripts/build_ui.ps1 (ou `npm run build` em "
    "frontend/) e recarregue."
)


def dist_available() -> bool:
    """True quando existe um build servível."""
    return UI_INDEX.is_file()


def media_type_for(path: Path) -> str | None:
    """Tipo MIME explícito por extensão; None deixa o Starlette adivinhar."""
    return MEDIA_TYPES.get(path.suffix.lower())


def resolve_dist_file(relative: str) -> Path | None:
    """Arquivo dentro de `UI_DIST` correspondente ao caminho pedido, ou None.

    Recusa caminhos vazios, com `..`, barra invertida, NUL ou que resolvam fora do dist
    (links simbólicos inclusive). Diretórios não contam como arquivo.
    """
    if not relative or "\\" in relative or "\x00" in relative:
        return None
    parts = [p for p in relative.split("/") if p]
    if not parts or any(p in ("..", ".") for p in parts):
        return None
    root = UI_DIST.resolve()
    try:
        candidate = root.joinpath(*parts).resolve()
    except (OSError, ValueError):
        return None
    if not candidate.is_relative_to(root):
        return None
    return candidate if candidate.is_file() else None


def cache_control_for(relative: str) -> str:
    """Assets com hash no nome são imutáveis; o resto é revalidado sempre."""
    return CACHE_IMMUTABLE if relative.startswith(UI_ASSETS_PREFIX) else CACHE_NO_CACHE


def _app_index() -> FileResponse:
    return FileResponse(
        UI_INDEX,
        media_type=MEDIA_TYPES[".html"],
        headers={"Cache-Control": CACHE_NO_CACHE},
    )


def _static_index() -> FileResponse:
    return FileResponse(
        INDEX_HTML,
        media_type=MEDIA_TYPES[".html"],
        headers={"Cache-Control": CACHE_NO_CACHE},
    )


@router.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """App compilado quando existe; senão a página estática de estado do Edge."""
    if dist_available():
        return _app_index()
    return _static_index()


@router.get("/app", include_in_schema=False)
@router.get("/app/", include_in_schema=False)
@router.get("/app/{path:path}", include_in_schema=False)
async def app_shell(path: str = "") -> FileResponse:
    """Arquivo do build quando existe; qualquer outra rota sob /app cai no index (SPA)."""
    if not dist_available():
        raise ApiError(404, "UI_NOT_BUILT", UI_NOT_BUILT_PT, {"dist": str(UI_DIST)})
    found = resolve_dist_file(path)
    if found is not None and found != UI_INDEX:
        return FileResponse(
            found,
            media_type=media_type_for(found),
            headers={"Cache-Control": cache_control_for(path)},
        )
    return _app_index()
