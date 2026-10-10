"""Ponto de entrada do executável empacotado (ForjaKCM.exe): a mesma linha de comando `forja`.

Sem argumentos (duplo clique), explica onde está a interface e fecha: quem roda o Edge é o
serviço do Windows, instalado pelo install.ps1.
"""

from __future__ import annotations

import sys

from forja.tools.cli import main

NO_ARGS_PT = (
    "Forja KCM Intelligence (somente leitura)\n"
    "O Edge roda como serviço do Windows (Forja KCM Intelligence).\n"
    "Abra a interface pelo atalho 'Forja KCM' ou em http://127.0.0.1:8765/app\n"
    "Comandos de administração: ForjaKCM.exe --help"
)


def explain_and_wait() -> int:
    """Duplo clique: mostra onde está a interface e espera Enter antes de fechar a janela."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")
    print(NO_ARGS_PT)
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nPressione Enter para fechar.")
        except (EOFError, OSError):  # entrada redirecionada para um dispositivo sem teclado
            pass
    return 0


if __name__ == "__main__":
    sys.exit(explain_and_wait() if len(sys.argv) == 1 else main())
