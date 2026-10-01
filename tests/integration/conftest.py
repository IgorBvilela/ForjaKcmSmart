"""Fixtures compartilhadas dos testes de integração.

`world` e `client` montam a API sobre um Container de fakes locais (tests/integration/api_testkit).
"""

from tests.integration.api_testkit import client, world

__all__ = ["client", "world"]
