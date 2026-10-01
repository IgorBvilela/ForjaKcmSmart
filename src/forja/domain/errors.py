"""Hierarquia unica de erros do dominio."""

from __future__ import annotations


class ForjaError(Exception):
    """Base de todos os erros do produto."""


class ReadOnlyContractViolation(ForjaError):
    """Alguem tentou colocar escrita onde o produto so le. Falha na definicao, nao em runtime."""


class DriverError(ForjaError):
    """Base dos erros de driver."""


class DriverConnectError(DriverError):
    pass


class DriverReadError(DriverError):
    pass


class DriverTimeout(DriverError):
    pass


class UnsupportedDriver(DriverError):
    pass


class ConfigError(ForjaError):
    pass


class MappingValidationError(ConfigError):
    pass


class HistorianError(ForjaError):
    pass


class NotConfigured(ForjaError):
    """Funcionalidade existe mas depende de configuracao de campo ainda UNKNOWN."""
