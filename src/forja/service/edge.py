"""Executor do Forja Edge: monta o container, liga o log em arquivo, sobe a API (uvicorn) e a
aquisição, e para de forma graciosa.

Usado por `forja run` (terminal) e pelo serviço Windows. `request_stop()` pode ser chamado de
outra thread (o gerenciador de serviços do Windows chama SvcStop fora do loop).
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Callable
from typing import Any

from forja.config import ForjaPaths

logger = logging.getLogger(__name__)

PORT_TRIES = 20


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def first_free_port(host: str, start: int, tries: int = PORT_TRIES) -> int:
    for candidate in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, candidate))
            except OSError:
                continue
            return candidate
    raise OSError(f"nenhuma porta livre entre {start} e {start + tries - 1} em {host}")


class EdgeRunner:
    """Um Edge em execução. `run()` só volta depois da parada graciosa."""

    def __init__(
        self,
        paths: ForjaPaths,
        host: str | None = None,
        port: int | None = None,
        *,
        announce: Callable[[str], None] = print,
        warn: Callable[[str], None] = logger.warning,
        console_log: bool = True,
    ) -> None:
        self._paths = paths
        self._host = host
        self._port = port
        self._announce = announce
        self._warn = warn
        self._console_log = console_log
        self._loop: asyncio.AbstractEventLoop | None = None
        self._server: Any = None
        self._stop_requested = False
        self.bound_port: int | None = None

    def request_stop(self) -> None:
        """Pede a parada graciosa. Seguro de chamar de qualquer thread."""
        self._stop_requested = True
        loop, server = self._loop, self._server
        if loop is not None and server is not None:
            loop.call_soon_threadsafe(setattr, server, "should_exit", True)

    async def run(self) -> None:
        import uvicorn

        from forja.api.app import create_app
        from forja.service.logsetup import configure_logging
        from forja.service.runner import build_container, start, stop

        container = await build_container(self._paths)
        configure_logging(
            self._paths.logs_dir, container.store.config.logging, console=self._console_log
        )
        edge = container.store.config.edge
        bind_host = self._host or edge.bind_host
        bind_port = self._port or edge.bind_port
        if not is_loopback(bind_host):
            self._warn(
                f"AVISO: bind em {bind_host!r} expõe o Edge fora desta máquina. "
                "O padrão do produto é 127.0.0.1."
            )
        free_port = first_free_port(bind_host, bind_port)
        if free_port != bind_port:
            self._warn(
                f"AVISO: porta {bind_port} ocupada por outro programa nesta máquina; usando "
                f"{free_port}. Para fixar, ajuste edge.bind_port em config/forja.yaml."
            )
            bind_port = free_port
        self.bound_port = bind_port
        app = create_app(container)
        config = uvicorn.Config(
            app,
            host=bind_host,
            port=bind_port,
            log_level=container.store.config.logging.level.lower(),
            lifespan="on",
        )
        server = uvicorn.Server(config)
        self._loop = asyncio.get_running_loop()
        self._server = server
        if self._stop_requested:
            server.should_exit = True
        await start(container)
        self._announce(
            f"Forja Edge em http://{bind_host}:{bind_port} · {len(container.store.profiles)} "
            "equipamento(s) · somente leitura"
        )
        logger.info("Forja Edge em http://%s:%s", bind_host, bind_port)
        try:
            await server.serve()
        finally:
            await stop(container)
            logger.info("Forja Edge parado")
            self._announce("Forja Edge parado.")


__all__ = ["EdgeRunner", "first_free_port", "is_loopback"]
