"""Serviço Windows do Forja Edge (pywin32), registrado pelo instalador com `sc.exe`.

O executável empacotado é chamado pelo gerenciador de serviços como
`ForjaKCM.exe service run`; aqui ele entrega o controle ao despachante do Windows, que chama
SvcDoRun (sobe o Edge) e SvcStop (parada graciosa: loops, gravação pendente e bancos fechados).
O serviço lê o KCM; não comanda nada.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from forja.config import resolve_paths

SERVICE_NAME = "ForjaKCM"
DISPLAY_NAME = "Forja KCM Intelligence"
DESCRIPTION = (
    "Observador somente leitura de controladores KCM: coleta, histórico, eventos e diagnóstico. "
    "Não envia comando ao equipamento."
)

logger = logging.getLogger(__name__)


def service_class() -> type[Any]:
    """Classe do serviço. Importa o pywin32 só quando o Windows realmente vai hospedar."""
    import servicemanager
    import win32service
    import win32serviceutil

    from forja.service.edge import EdgeRunner

    class ForjaService(win32serviceutil.ServiceFramework):  # type: ignore[misc]
        _svc_name_ = SERVICE_NAME
        _svc_display_name_ = DISPLAY_NAME
        _svc_description_ = DESCRIPTION

        def __init__(self, args: Any) -> None:
            super().__init__(args)
            self._runner: EdgeRunner | None = None

        def SvcStop(self) -> None:  # noqa: N802 - nome exigido pelo pywin32
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            if self._runner is not None:
                self._runner.request_stop()

        def SvcDoRun(self) -> None:  # noqa: N802 - nome exigido pelo pywin32
            servicemanager.LogInfoMsg(f"{DISPLAY_NAME}: iniciando (somente leitura)")
            self._runner = EdgeRunner(
                resolve_paths(),
                announce=lambda message: servicemanager.LogInfoMsg(message),
                warn=lambda message: servicemanager.LogWarningMsg(message),
                console_log=False,
            )
            try:
                asyncio.run(self._runner.run())
            except Exception as exc:
                servicemanager.LogErrorMsg(f"{DISPLAY_NAME}: parou com erro: {exc}")
                raise
            servicemanager.LogInfoMsg(f"{DISPLAY_NAME}: parado")

    return ForjaService


def run_as_service() -> int:
    """Entrega o processo ao gerenciador de serviços do Windows."""
    import servicemanager

    # Fonte do Visualizador de Eventos com o nome do serviço; as mensagens vêm do próprio
    # módulo servicemanager (o instalador registra essa fonte, que exige administrador).
    servicemanager.Initialize(SERVICE_NAME, servicemanager.__file__)
    servicemanager.PrepareToHostSingle(service_class())
    servicemanager.StartServiceCtrlDispatcher()
    return 0


__all__ = ["DESCRIPTION", "DISPLAY_NAME", "SERVICE_NAME", "run_as_service", "service_class"]
