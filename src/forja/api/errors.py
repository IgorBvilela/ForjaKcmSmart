"""Envelope único de erro da API: {"error": {"code", "message_pt", "details"}}.

Nenhum traceback sai para o cliente. O código interno vai em `code`; o texto para o usuário em
`message_pt`. `details` é opcional e já saneado (sem corpo ecoado, sem objetos Python).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("forja.api")

_STATUS_CODE: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    501: "NOT_IMPLEMENTED",
    503: "SERVICE_UNAVAILABLE",
}

_STATUS_MESSAGE_PT: dict[int, str] = {
    400: "Requisição inválida.",
    401: "Não autenticado.",
    403: "Acesso negado.",
    404: "Rota não encontrada.",
    405: "Método não permitido nesta rota.",
    409: "Conflito com o estado atual.",
    413: "Corpo da requisição acima do limite permitido.",
    415: "Tipo de conteúdo não suportado.",
    422: "Dados da requisição inválidos.",
    429: "Muitas requisições.",
    500: "Erro interno do Edge. Consulte o log local.",
    501: "Funcionalidade não implementada.",
    503: "Serviço indisponível no momento.",
}


class ApiError(Exception):
    """Erro de negócio da API, já com status HTTP, código e texto em português."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message_pt: str,
        details: Any = None,
    ) -> None:
        super().__init__(message_pt)
        self.status_code = status_code
        self.code = code
        self.message_pt = message_pt
        self.details = details


def envelope(code: str, message_pt: str, details: Any = None) -> dict[str, Any]:
    """Monta o envelope de erro."""
    return {"error": {"code": code, "message_pt": message_pt, "details": details}}


def error_response(
    status_code: int, code: str, message_pt: str, details: Any = None
) -> JSONResponse:
    """Resposta JSON com envelope de erro."""
    return JSONResponse(status_code=status_code, content=envelope(code, message_pt, details))


def internal_error_response() -> JSONResponse:
    """Envelope 500 padrão. Sem traceback, sem detalhe: o log local tem o resto."""
    return error_response(500, "INTERNAL_ERROR", _STATUS_MESSAGE_PT[500])


def _sanitize_validation_errors(errors: list[Any]) -> list[dict[str, Any]]:
    """Mantém só loc/msg/type. Nunca ecoa o corpo recebido (`input`) nem objetos de contexto."""
    out: list[dict[str, Any]] = []
    for err in errors[:50]:
        if not isinstance(err, dict):
            continue
        out.append(
            {
                "loc": [str(p) for p in err.get("loc", ())],
                "msg": str(err.get("msg", "")),
                "type": str(err.get("type", "")),
            }
        )
    return out


def install_error_handlers(app: FastAPI) -> None:
    """Registra os handlers que convertem qualquer exceção no envelope único."""

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message_pt, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            "VALIDATION_ERROR",
            _STATUS_MESSAGE_PT[422],
            _sanitize_validation_errors(list(exc.errors())),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _STATUS_CODE.get(exc.status_code, "HTTP_ERROR")
        message_pt = _STATUS_MESSAGE_PT.get(exc.status_code, "Erro HTTP.")
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(code, message_pt, None),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, _exc: Exception) -> JSONResponse:
        # Fallback: em operação normal o SecurityHeadersMiddleware captura antes (com cabeçalhos).
        logger.exception("erro não tratado em %s %s", request.method, request.url.path)
        return internal_error_response()
