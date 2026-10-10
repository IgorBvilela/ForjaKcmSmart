"""Fixtures compartilhadas dos testes de integração.

`world` e `client` montam a API sobre um Container de fakes locais (tests/integration/api_testkit).
`cfg_world` e `cfg_client` fazem o mesmo com a configuração copiada para uma pasta temporária,
para testes que gravam configuração.
"""

from tests.integration.api_testkit import cfg_client, cfg_world, client, world

__all__ = ["cfg_client", "cfg_world", "client", "world"]
