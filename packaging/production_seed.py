"""Semente de configuração do pacote: a do repositório com o nome de produção do Edge.

A semente do repositório é a de desenvolvimento: o nome do Edge contém "desenvolvimento", o que
liga /docs (forja.api.deps.is_dev_mode). O pacote leva a mesma configuração com o nome de
produção. Se o arquivo de origem mudar e a troca não for exata, o build para.
"""

from __future__ import annotations

DEV_HEADER = (
    "# Configuracao do Forja Edge. Semente de desenvolvimento.\n"
    "# Em producao, copiada para %ProgramData%\\ForjaKCM\\config (fase N).\n"
)
PRODUCTION_HEADER = "# Configuracao do Forja Edge.\n"
DEV_NAME = 'name: "Forja Edge (desenvolvimento)"'
PRODUCTION_NAME = 'name: "Forja Edge"'


def production_config(source_text: str) -> str:
    """Texto do forja.yaml do pacote. ValueError quando a origem não tem o formato esperado."""
    if DEV_HEADER not in source_text or source_text.count(DEV_NAME) != 1:
        raise ValueError("config/forja.yaml mudou: revise a troca para a semente de produção")
    return source_text.replace(DEV_HEADER, PRODUCTION_HEADER).replace(DEV_NAME, PRODUCTION_NAME)
