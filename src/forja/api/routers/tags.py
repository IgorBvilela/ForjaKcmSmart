"""Catálogo das variáveis semânticas (rótulo em português, unidade, tipo e casas decimais)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from forja.domain import TAGS

router = APIRouter(prefix="/api/v1", tags=["variaveis"])


@router.get("/tags")
async def list_tags() -> dict[str, Any]:
    """Todas as variáveis semânticas conhecidas. Nem toda máquina expõe todas: o mapping diz."""
    return {
        "tags": [
            {
                "code": t.code,
                "label_pt": t.label_pt,
                "unit": t.unit,
                "kind": t.kind.value,
                "decimals": t.decimals,
                "explanation_pt": t.explanation_pt,
            }
            for t in TAGS.values()
        ]
    }
