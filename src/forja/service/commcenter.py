"""Central de Comunicação KCM: regras de negócio usadas pela API e pela CLI.

- ``validate_candidate``: confere perfil + mapping sem tocar na rede (erros bloqueiam, avisos não).
- ``reading_fingerprint``: identifica o que de fato muda a leitura (driver, endereço, mapping).
  Um teste somente leitura vale para a configuração com o mesmo fingerprint.
- ``comm_state``: o estado de configuração mostrado na tela (não configurado, experimental,
  teste OK, erro de comunicação...).
- ``address_text_pt`` e ``read_test_view``: o que foi lido, onde, bruto e decodificado.
Nada aqui escreve no equipamento: não existe função para isso.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Final

from forja.domain import (
    REAL_DRIVERS,
    UNKNOWN,
    ConfigError,
    ConnectionState,
    DriverSupportState,
    EquipmentProfile,
    EquipmentRuntimeStatus,
    Mapping,
    MappingEntry,
    MappingValidationError,
    Sample,
    UnsupportedDriver,
    get_tag,
    is_known_tag,
)

MODBUS_AREA_PT: Final[dict[str, str]] = {
    "holding": "Holding register (função 03)",
    "input": "Input register (função 04)",
    "coil": "Coil (função 01)",
    "discrete": "Discrete input (função 02)",
}

ENDIANNESS_PT: Final[dict[str, str]] = {
    "big": "ABCD (big-endian)",
    "little": "DCBA (little-endian)",
    "big_word_swap": "CDAB (palavras trocadas)",
    "little_word_swap": "BADC (bytes trocados na palavra)",
}

SHORT_POLL_S: Final[float] = 0.5


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blocks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "blocks": list(self.blocks),
            "requests_per_cycle": len(self.blocks),
        }


# ----------------------------------------------------------------------------- fingerprint


def _entry_reading_view(e: MappingEntry) -> dict[str, Any]:
    return {
        "tag": e.semantic_tag,
        "address": e.protocol_address,
        "datatype": str(e.datatype),
        "endianness": str(e.endianness),
        "scale": e.scale.model_dump() if hasattr(e.scale, "model_dump") else str(e.scale),
        "valid_min": e.valid_min,
        "valid_max": e.valid_max,
    }


def reading_fingerprint(profile: EquipmentProfile, mapping: Mapping) -> str:
    """sha256 do que muda a leitura. Fica de fora: coleta ligada, notas, versão, validações."""
    comm = profile.communication
    view = {
        "equipment_id": profile.id,
        "driver": comm.driver,
        "protocol": comm.protocol,
        "ip": comm.ip,
        "port": comm.port,
        "unit_id": comm.unit_id,
        "timeout_s": comm.timeout_s,
        "connect_timeout_s": comm.connect_timeout_s,
        "max_block_size": comm.max_block_size,
        "options": comm.options,
        "mapping_id": mapping.mapping_id,
        "mapping_driver": mapping.driver,
        "entries": [_entry_reading_view(e) for e in mapping.entries],
    }
    canonical = json.dumps(view, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- endereço em texto


def address_text_pt(driver: str, entry: MappingEntry) -> str:
    """Onde a tag é lida, em português, exatamente como está no mapping (nada convertido)."""
    addr = entry.protocol_address
    if addr == UNKNOWN:
        return "endereço não informado"
    if driver == "simulator":
        return f"simulador ({addr})"
    if not isinstance(addr, dict):
        return str(addr)
    if driver == "modbus_tcp":
        area = str(addr.get("area", "?"))
        parts = [f"{MODBUS_AREA_PT.get(area, area)}, endereço {addr.get('address', '?')}"]
        count = addr.get("count")
        if isinstance(count, int) and count > 1:
            parts.append(f"{count} registradores")
        if addr.get("bit") is not None:
            parts.append(f"bit {addr.get('bit')}")
        return " · ".join(parts)
    if driver == "ethernet_ip":
        return (
            f"classe {addr.get('class', '?')}, instância {addr.get('instance', '?')}, "
            f"atributo {addr.get('attribute', '?')}, byte {addr.get('offset', 0)}, "
            f"{addr.get('length', '?')} byte(s)"
        )
    return json.dumps(addr, ensure_ascii=False)


# ----------------------------------------------------------------------------- validação


def _driver_problems(profile: EquipmentProfile) -> list[str]:
    comm = profile.communication
    if comm.driver == UNKNOWN or (comm.protocol == UNKNOWN and comm.driver != "simulator"):
        return ["Protocolo ainda não identificado: confirme no KCM (versões / Host) antes."]
    if comm.driver in REAL_DRIVERS and comm.protocol != comm.driver:
        return [
            f"Protocolo {comm.protocol!r} não corresponde ao driver {comm.driver!r}. "
            "Escolha o protocolo de novo."
        ]
    try:
        if comm.driver == "modbus_tcp":
            from forja.drivers.modbus_tcp.driver import modbus_settings

            modbus_settings(profile)
        elif comm.driver == "ethernet_ip":
            try:
                from forja.drivers.ethernet_ip.driver import eip_settings
            except ImportError:
                return ["Driver EtherNet/IP indisponível nesta instalação."]
            eip_settings(profile)
    except ConfigError as exc:
        return [str(exc).split(": ", 1)[-1]]
    return []


def _mapping_warnings(profile: EquipmentProfile, mapping: Mapping) -> list[str]:
    out: list[str] = []
    readable = mapping.readable_entries
    if not readable:
        out.append("Nenhuma variável com endereço e tipo: não há o que ler.")
    unknown = [e.semantic_tag for e in mapping.unknown_entries]
    if unknown:
        out.append(f"{len(unknown)} variável(is) sem endereço ou tipo serão ignoradas na leitura.")
    if profile.communication.driver in REAL_DRIVERS:
        no_source = [e for e in readable if e.source == UNKNOWN]
        if no_source:
            out.append(
                f"{len(no_source)} variável(is) sem fonte do endereço (documento, captura ou "
                "teste autorizado): as leituras ficam como 'Não validado'."
            )
        no_scale = [e for e in readable if e.scale == UNKNOWN]
        if no_scale:
            out.append(
                f"{len(no_scale)} variável(is) sem escala: valor lido sai sem conversão de "
                "engenharia."
            )
        if readable and not any(e.confirmed for e in readable):
            out.append("Nenhuma variável conferida ainda contra a tela do KCM.")
    return out


def validate_candidate(
    profile: EquipmentProfile,
    mapping: Mapping,
    support: dict[str, Any] | None = None,
) -> ValidationReport:
    """Confere a configuração sem abrir conexão. ``support``: {driver: info} do registry."""
    from forja.normalization.plan import ReadPlanCompiler

    report = ValidationReport()
    comm = profile.communication
    report.errors += _driver_problems(profile)
    if support is not None and comm.driver in support:
        state = getattr(support[comm.driver], "state", None)
        if str(state) == DriverSupportState.UNSUPPORTED.value:
            report.errors.append("Driver indisponível nesta instalação.")
        elif str(state) == DriverSupportState.EXPERIMENTAL.value:
            report.warnings.append(
                "Driver experimental: validado em bancada, ainda não contra o KCM real."
            )
    if mapping.equipment_id not in ("*", profile.id):
        report.errors.append("O mapping pertence a outro equipamento.")
    if comm.poll_interval_s < SHORT_POLL_S and comm.driver in REAL_DRIVERS:
        report.warnings.append(
            "Intervalo de leitura curto: confirme com a planta se o módulo Host suporta."
        )
    if comm.driver == "modbus_tcp" and comm.unit_id == 0:
        report.warnings.append("Unit id 0 é endereço de difusão em alguns equipamentos.")
    report.warnings += _mapping_warnings(profile, mapping)
    if comm.driver != UNKNOWN and not report.errors:
        try:
            plan = ReadPlanCompiler().compile(profile, mapping)
        except (MappingValidationError, ConfigError, UnsupportedDriver) as exc:
            report.errors.append(f"Mapping incompatível: {exc}")
        else:
            report.blocks = [
                {
                    "block_id": b.block_id,
                    "area": b.area,
                    "address": b.address,
                    "count": b.count,
                    "tags": list(b.tags),
                }
                for b in plan.blocks
            ]
    return report


# ----------------------------------------------------------------------------- estado


STATE_PT: Final[dict[str, tuple[str, str]]] = {
    "NOT_CONFIGURED": ("Não configurado", "unknown"),
    "PROTOCOL_UNKNOWN": ("Protocolo ainda não identificado", "unknown"),
    "UNSUPPORTED": ("Driver indisponível", "crit"),
    "NEEDS_CONFIGURATION": ("Configuração necessária", "warn"),
    "SIMULATED": ("Simulador (demonstração)", "sim"),
    "DRIVER_AVAILABLE": ("Driver disponível", "info"),
    "EXPERIMENTAL": ("Driver experimental: teste a leitura", "warn"),
    "READ_TEST_OK": ("Teste de leitura OK", "ok"),
    "READ_TEST_FAILED": ("Teste de leitura falhou", "crit"),
    "COMM_ERROR": ("Erro de comunicação", "crit"),
    "COLLECTING": ("Coletando (somente leitura)", "ok"),
}


def comm_state(
    profile: EquipmentProfile,
    support_state: str | None,
    status: EquipmentRuntimeStatus | None,
    last_test: dict[str, Any] | None,
    fingerprint: str,
) -> dict[str, Any]:
    """Estado de configuração da comunicação, do mais básico ao mais avançado."""
    comm = profile.communication
    code: str
    if comm.driver == UNKNOWN or (comm.driver != "simulator" and comm.protocol == UNKNOWN):
        code = "PROTOCOL_UNKNOWN"
    elif support_state == DriverSupportState.UNSUPPORTED.value:
        code = "UNSUPPORTED"
    elif comm.needs_configuration:
        code = "NEEDS_CONFIGURATION"
    elif comm.driver == "simulator":
        code = "SIMULATED"
    elif (
        comm.collection_enabled
        and status is not None
        and status.connection is (ConnectionState.ERROR)
    ):
        code = "COMM_ERROR"
    elif (
        comm.collection_enabled
        and status is not None
        and status.connection is (ConnectionState.CONNECTED)
    ):
        code = "COLLECTING"
    elif last_test is not None and last_test.get("fingerprint") == fingerprint:
        code = "READ_TEST_OK" if last_test.get("success") else "READ_TEST_FAILED"
    elif support_state == DriverSupportState.EXPERIMENTAL.value:
        code = "EXPERIMENTAL"
    else:
        code = "DRIVER_AVAILABLE"
    label, tone = STATE_PT[code]
    return {"code": code, "label_pt": label, "tone": tone}


# ----------------------------------------------------------------------------- teste de leitura


def _decoded_text(tag: str, sample: Sample) -> str | None:
    if sample.value is None:
        return None
    meta = get_tag(tag) if is_known_tag(tag) else None
    decimals = meta.decimals if meta else 3
    text = f"{sample.value:.{decimals}f}".replace(".", ",")
    return f"{text} {meta.unit}".strip() if meta and meta.unit else text


def read_test_view(
    result: Any, profile: EquipmentProfile, mapping: Mapping, plan_blocks: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resultado do teste para a tela: por variável, onde leu, bruto, decodificado e qualidade."""
    values: dict[str, Sample] = dict(getattr(result, "values", {}) or {})
    block_of = {tag: b for b in plan_blocks for tag in b.get("tags", [])}
    rows: list[dict[str, Any]] = []
    for entry in mapping.readable_entries:
        tag = entry.semantic_tag
        sample = values.get(tag)
        meta = get_tag(tag) if is_known_tag(tag) else None
        rows.append(
            {
                "tag": tag,
                "label_pt": meta.label_pt if meta else tag,
                "unit": meta.unit if meta else "",
                "address_pt": address_text_pt(profile.communication.driver, entry),
                "block_id": block_of.get(tag, {}).get("block_id"),
                "datatype": str(entry.datatype),
                "endianness_pt": ENDIANNESS_PT.get(str(entry.endianness), str(entry.endianness)),
                "raw_hex": sample.raw.hex(" ") if sample is not None and sample.raw else None,
                "value": None if sample is None else sample.value,
                "value_pt": None if sample is None else _decoded_text(tag, sample),
                "quality": None if sample is None else sample.quality.value,
                "quality_pt": None if sample is None else sample.quality.label_pt,
                "reason_pt": None if sample is None else sample.reason_pt,
                "confirmed": entry.confirmed,
            }
        )
    return {"tags": rows, "blocks": plan_blocks}


__all__ = [
    "ENDIANNESS_PT",
    "MODBUS_AREA_PT",
    "STATE_PT",
    "ValidationReport",
    "address_text_pt",
    "comm_state",
    "read_test_view",
    "reading_fingerprint",
    "validate_candidate",
]
