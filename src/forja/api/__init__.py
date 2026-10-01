"""API HTTP do Forja Edge: REST + SSE, somente leitura do KCM por construção.

Nenhuma rota comanda o equipamento. O que muta é: reconhecimento de evento (auditado),
teste de leitura (descartável) e controles do simulador (nunca chegam ao KCM).
"""

from forja.api.app import create_app

__all__ = ["create_app"]
