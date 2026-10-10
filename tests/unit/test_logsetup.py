"""Log do serviço em arquivo com rotação, e leitura do final do arquivo por nível."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from forja.config.models import LoggingConfig
from forja.service.logsetup import LOG_FILE_NAME, configure_logging, read_log_tail

pytestmark = pytest.mark.unit


def test_grava_em_arquivo_e_le_o_final_por_nivel(tmp_path: Path) -> None:
    handler = configure_logging(
        tmp_path, LoggingConfig(level="INFO", rotate_mb=1, keep=2), console=False
    )
    try:
        log = logging.getLogger("forja.teste")
        log.info("leitura ok")
        log.warning("sem resposta do equipamento")
        try:
            raise ValueError("falha de teste")
        except ValueError:
            log.exception("erro inesperado")
        handler.flush()
        path = tmp_path / LOG_FILE_NAME
        assert path.is_file()
        entries = read_log_tail(path, limit=10)
        assert [e["level"] for e in entries] == ["ERROR", "WARNING", "INFO"]
        assert entries[0]["message"] == "erro inesperado"
        assert "ValueError" in entries[0]["detail"]
        assert entries[1]["logger"] == "forja.teste"
        warnings = read_log_tail(path, limit=10, min_level="WARNING")
        assert [e["level"] for e in warnings] == ["ERROR", "WARNING"]
    finally:
        logging.getLogger().removeHandler(handler)
        handler.close()


def test_arquivo_inexistente_devolve_vazio(tmp_path: Path) -> None:
    assert read_log_tail(tmp_path / "nao_existe.log", limit=10) == []


def test_reconfigurar_nao_duplica_handler(tmp_path: Path) -> None:
    root = logging.getLogger()
    before = len(root.handlers)
    first = configure_logging(tmp_path, LoggingConfig(), console=False)
    second = configure_logging(tmp_path, LoggingConfig(), console=False)
    try:
        assert len(root.handlers) == before + 1
        assert first is not second
    finally:
        root.removeHandler(second)
        second.close()
        first.close()
