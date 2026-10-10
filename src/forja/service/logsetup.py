"""Log do serviço em arquivo (com rotação) e leitura do final do arquivo para a tela de Logs.

Formato de linha: ``<instante ISO> <NÍVEL> <logger>: <mensagem>``. Linhas seguintes sem esse
prefixo (traceback) pertencem à entrada anterior e voltam como ``detail``.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Final

from forja.config.models import LoggingConfig

LOG_FILE_NAME: Final[str] = "forja.log"
LINE_FORMAT: Final[str] = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S%z"
_HANDLER_NAME: Final[str] = "forja-arquivo"
_LINE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}) (?P<level>[A-Z]+) "
    r"(?P<logger>[^:]+): (?P<message>.*)$"
)
_LEVELS: Final[dict[str, int]] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}
MAX_TAIL_BYTES: Final[int] = 4 * 1024 * 1024


def configure_logging(
    logs_dir: Path, config: LoggingConfig, *, console: bool = True
) -> RotatingFileHandler:
    """Liga o arquivo de log do serviço. Chamar de novo troca o handler (não duplica)."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    for existing in [h for h in root.handlers if h.get_name() == _HANDLER_NAME]:
        root.removeHandler(existing)
        existing.close()
    handler = RotatingFileHandler(
        logs_dir / LOG_FILE_NAME,
        maxBytes=max(1, config.rotate_mb) * 1024 * 1024,
        backupCount=max(1, config.keep),
        encoding="utf-8",
    )
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LINE_FORMAT, DATE_FORMAT))
    root.addHandler(handler)
    root.setLevel(_LEVELS.get(config.level.upper(), logging.INFO))
    if console and not any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    ):
        stream = logging.StreamHandler()
        stream.setFormatter(logging.Formatter(LINE_FORMAT, DATE_FORMAT))
        root.addHandler(stream)
    return handler


def read_log_tail(
    path: Path, *, limit: int = 200, min_level: str | None = None
) -> list[dict[str, Any]]:
    """Últimas entradas do arquivo (mais recentes primeiro), opcionalmente a partir de um nível."""
    if not path.is_file():
        return []
    threshold = _LEVELS.get((min_level or "").upper(), logging.NOTSET)
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size > MAX_TAIL_BYTES:
            fh.seek(size - MAX_TAIL_BYTES)
            fh.readline()
        text = fh.read().decode("utf-8", errors="replace")
    entries: deque[dict[str, Any]] = deque()
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = _LINE.match(line)
        if match:
            current = {**match.groupdict(), "detail": ""}
            ts = current["ts"]
            current["ts"] = f"{ts[:-2]}:{ts[-2:]}"  # -0300 -> -03:00 (ISO 8601 completo)
            entries.append(current)
        elif current is not None and line.strip():
            current["detail"] = (current["detail"] + "\n" + line).strip("\n")
    picked = [e for e in reversed(entries) if _LEVELS.get(e["level"], 0) >= threshold]
    return picked[: max(1, limit)]


__all__ = ["LOG_FILE_NAME", "configure_logging", "read_log_tail"]
