# Empacotamento PyInstaller (onedir) do Forja KCM Intelligence.
# Gera dist/ForjaKCM/ForjaKCM.exe com a interface compilada, as migrações dos bancos e a semente
# de configuração (config/ e knowledge/) em seed/. Rodar pelo scripts/build_windows.ps1.

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
SRC = ROOT / "src"
UI_DIST = SRC / "forja" / "ui" / "dist"
SEED_BUILD = ROOT / "build" / "seed"

if not (UI_DIST / "index.html").is_file():
    raise SystemExit("interface não compilada: rode `npm run build` em frontend/ antes")

# Semente de produção: o forja.yaml do repositório sem o modo desenvolvimento (production_seed.py).
sys.path.insert(0, SPECPATH)
from production_seed import production_config  # noqa: E402

try:
    seed_text = production_config((ROOT / "config" / "forja.yaml").read_text(encoding="utf-8"))
except ValueError as exc:
    raise SystemExit(str(exc)) from exc
SEED_BUILD.mkdir(parents=True, exist_ok=True)
(SEED_BUILD / "forja.yaml").write_text(seed_text, encoding="utf-8")


def tree(source: Path, dest: str, skip: tuple[str, ...] = ("_history", "__pycache__")) -> list:
    """Arquivos de uma pasta para `datas`, sem pastas de histórico local nem cache."""
    out = []
    for item in sorted(source.rglob("*")):
        if not item.is_file() or any(part in skip for part in item.parts):
            continue
        rel = item.parent.relative_to(source).as_posix()
        out.append((str(item), f"{dest}/{rel}" if rel != "." else dest))
    return out


datas = [
    *tree(UI_DIST, "forja/ui/dist"),
    *tree(SRC / "forja" / "api" / "static", "forja/api/static"),
    *tree(SRC / "forja" / "historian" / "migrations", "forja/historian/migrations"),
    *[item for item in tree(ROOT / "config", "seed/config") if Path(item[0]).name != "forja.yaml"],
    (str(SEED_BUILD / "forja.yaml"), "seed/config"),
    *tree(ROOT / "knowledge", "seed/knowledge"),
]

hiddenimports = [
    *collect_submodules("forja"),
    *collect_submodules("uvicorn"),
    "win32timezone",
    "servicemanager",
    "win32serviceutil",
    "win32service",
    "win32event",
]

a = Analysis(
    [str(ROOT / "packaging" / "forja_main.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "hypothesis", "playwright", "mypy", "ruff", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ForjaKCM",
    console=True,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="ForjaKCM")
