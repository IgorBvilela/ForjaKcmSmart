"""Compila (perfil, mapping) em um ReadPlan. Enderecos vem SO do mapping.

- simulator: 1 bloco "sim" com todas as entradas legiveis (payload dict, sem layout).
- modbus_tcp: coalesce entradas contiguas por area; layout {tag: {offset, count, unit}}.
  Limites 125 registradores / 2000 bits sao do protocolo Modbus, nao de nenhum equipamento.
- ethernet_ip: 1 bloco por atributo CIP (classe, instancia, atributo), com layout em bytes das
  tags que moram nele. Classe, instancia e atributo sao obrigatorios: vem do documento da
  maquina, nunca de valor padrao no codigo.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from forja.domain.assets import EquipmentProfile
from forja.domain.errors import MappingValidationError, UnsupportedDriver
from forja.domain.evidence import UNKNOWN
from forja.domain.mapping import BYTE_TYPES, DataType, Mapping, MappingEntry
from forja.domain.samples import ReadBlock, ReadPlan

SIM_AREA = "sim"
SIM_ADDRESS_PREFIX = "sim:"
MODBUS_AREAS: tuple[str, ...] = ("holding", "input", "coil", "discrete")
MODBUS_BIT_AREAS: tuple[str, ...] = ("coil", "discrete")
MODBUS_MAX_REGISTERS = 125
MODBUS_MAX_BITS = 2000
EIP_KINDS: tuple[str, ...] = ("assembly", "attribute")

LayoutUnit = str
"""'word' (registrador de 16 bits), 'bit' (coil/discrete) ou 'byte' (EtherNet/IP)."""


@dataclass(frozen=True)
class _Span:
    tag: str
    start: int
    count: int
    bit: int | None = None
    """Bit dentro do(s) registrador(es) (0 = menos significativo). Só em holding/input."""

    @property
    def end(self) -> int:
        return self.start + self.count


def layout_of(block: ReadBlock) -> dict[str, dict[str, Any]]:
    """Layout {tag: {offset, count, unit}} de um bloco; vazio para o simulador."""
    layout = block.meta.get("layout", {})
    return dict(layout) if isinstance(layout, dict) else {}


class ReadPlanCompiler:
    """Transforma mapping em blocos de leitura. Falha cedo em mapping incoerente."""

    def compile(self, profile: EquipmentProfile, mapping: Mapping) -> ReadPlan:
        driver = profile.communication.driver
        if mapping.driver not in (UNKNOWN, driver):
            raise MappingValidationError(
                f"{mapping.mapping_id}: mapping é do driver {mapping.driver!r}, "
                f"perfil {profile.id} usa {driver!r}"
            )
        if mapping.equipment_id not in ("*", profile.id):
            raise MappingValidationError(
                f"{mapping.mapping_id}: mapping é do equipamento {mapping.equipment_id!r}, "
                f"não de {profile.id}"
            )
        entries = mapping.readable_entries
        if driver == "simulator":
            blocks = self._simulator(entries)
        elif driver == "modbus_tcp":
            blocks = self._modbus(entries, profile)
        elif driver == "ethernet_ip":
            blocks = self._eip(entries)
        else:
            raise UnsupportedDriver(f"driver desconhecido no plano: {driver!r}")
        return ReadPlan(
            equipment_id=profile.id,
            mapping_id=mapping.mapping_id,
            mapping_version=mapping.version,
            blocks=tuple(blocks),
        )

    # --- simulador --------------------------------------------------------------------------

    def _simulator(self, entries: Sequence[MappingEntry]) -> list[ReadBlock]:
        tags: list[str] = []
        for e in entries:
            expected = f"{SIM_ADDRESS_PREFIX}{e.semantic_tag}"
            if e.protocol_address != expected:
                raise MappingValidationError(
                    f"{e.semantic_tag}: endereço do simulador deve ser {expected!r} "
                    f"(recebido {e.protocol_address!r})"
                )
            tags.append(e.semantic_tag)
        if not tags:
            return []
        return [
            ReadBlock(
                block_id=SIM_AREA,
                area=SIM_AREA,
                address=SIM_AREA,
                count=len(tags),
                tags=tuple(tags),
                meta={},
            )
        ]

    # --- modbus -----------------------------------------------------------------------------

    def _modbus(
        self, entries: Sequence[MappingEntry], profile: EquipmentProfile
    ) -> list[ReadBlock]:
        by_area: dict[str, list[_Span]] = {}
        for e in entries:
            area, span = self._modbus_span(e)
            by_area.setdefault(area, []).append(span)
        blocks: list[ReadBlock] = []
        coalesce = profile.communication.options.get("block_reads", True) is not False
        for area in MODBUS_AREAS:
            spans = by_area.get(area)
            if not spans:
                continue
            unit: LayoutUnit = "bit" if area in MODBUS_BIT_AREAS else "word"
            limit = self._modbus_limit(area, profile)
            ordered = sorted(spans, key=lambda s: (s.start, s.tag))
            groups = _coalesce(ordered, limit) if coalesce else _singles(ordered, limit)
            for group in groups:
                blocks.append(_block_from_group(area, group, unit))
        return blocks

    @staticmethod
    def _modbus_span(e: MappingEntry) -> tuple[str, _Span]:
        addr = e.protocol_address
        if not isinstance(addr, dict):
            raise MappingValidationError(
                f"{e.semantic_tag}: endereço Modbus deve ser dict {{area, address, count}}"
            )
        area = addr.get("area")
        if area not in MODBUS_AREAS:
            raise MappingValidationError(f"{e.semantic_tag}: area Modbus inválida: {area!r}")
        address = addr.get("address")
        if isinstance(address, bool) or not isinstance(address, int) or address < 0:
            raise MappingValidationError(f"{e.semantic_tag}: address Modbus inválido: {address!r}")
        if e.datatype in BYTE_TYPES:
            raise MappingValidationError(
                f"{e.semantic_tag}: tipo de 8 bits não existe em registrador Modbus (16 bits); "
                "use uint16 com bit ou escala"
            )
        count = addr.get("count", _default_count(e.datatype, area))
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise MappingValidationError(f"{e.semantic_tag}: count Modbus inválido: {count!r}")
        bit = addr.get("bit")
        if bit is not None:
            if area in MODBUS_BIT_AREAS:
                raise MappingValidationError(
                    f"{e.semantic_tag}: 'bit' só vale para registradores (holding/input)"
                )
            if count not in (1, 2):
                raise MappingValidationError(
                    f"{e.semantic_tag}: 'bit' exige 1 ou 2 registradores (count={count})"
                )
            if isinstance(bit, bool) or not isinstance(bit, int) or not 0 <= bit < 16 * count:
                raise MappingValidationError(
                    f"{e.semantic_tag}: bit fora de 0..{16 * count - 1}: {bit!r}"
                )
        return str(area), _Span(tag=e.semantic_tag, start=address, count=count, bit=bit)

    @staticmethod
    def _modbus_limit(area: str, profile: EquipmentProfile) -> int:
        protocol_limit = MODBUS_MAX_BITS if area in MODBUS_BIT_AREAS else MODBUS_MAX_REGISTERS
        configured = profile.communication.max_block_size
        if isinstance(configured, int) and not isinstance(configured, bool) and configured > 0:
            return min(configured, protocol_limit)
        return protocol_limit

    # --- ethernet/ip ------------------------------------------------------------------------

    def _eip(self, entries: Sequence[MappingEntry]) -> list[ReadBlock]:
        groups: dict[tuple[int, int, int], list[tuple[str, dict[str, Any]]]] = {}
        for e in entries:
            key, slot = _eip_slot(e)
            groups.setdefault(key, []).append((e.semantic_tag, slot))
        blocks: list[ReadBlock] = []
        for (cls, inst, attr), items in sorted(groups.items()):
            end = max(int(slot["offset"]) + int(slot["count"]) for _, slot in items)
            blocks.append(
                ReadBlock(
                    block_id=f"eip:{cls}:{inst}:{attr}",
                    area="attribute",
                    address=inst,
                    count=end,
                    tags=tuple(tag for tag, _ in items),
                    meta={
                        "class": cls,
                        "instance": inst,
                        "attribute": attr,
                        "layout": dict(items),
                    },
                )
            )
        return blocks


def _eip_slot(e: MappingEntry) -> tuple[tuple[int, int, int], dict[str, Any]]:
    """(classe, instância, atributo) e o recorte da tag dentro dos dados do atributo."""
    addr = e.protocol_address
    tag = e.semantic_tag
    if not isinstance(addr, dict):
        raise MappingValidationError(
            f"{tag}: endereço EtherNet/IP deve ser dict "
            "{kind, class, instance, attribute, offset, length}"
        )
    kind = addr.get("kind", "attribute")
    if kind not in EIP_KINDS:
        raise MappingValidationError(f"{tag}: kind EtherNet/IP inválido: {kind!r}")
    missing = [k for k in ("class", "instance", "attribute") if k not in addr]
    if missing:
        raise MappingValidationError(
            f"{tag}: EtherNet/IP sem {', '.join(missing)}; esses números vêm do documento da "
            "máquina e não têm valor padrão"
        )
    cls = _non_negative_int(tag, "class", addr["class"])
    inst = _non_negative_int(tag, "instance", addr["instance"])
    attr = _non_negative_int(tag, "attribute", addr["attribute"])
    if cls < 1 or attr < 1:
        raise MappingValidationError(f"{tag}: classe e atributo EtherNet/IP começam em 1")
    offset = _non_negative_int(tag, "offset", addr.get("offset", 0))
    if e.datatype == DataType.STRING and "length" not in addr:
        raise MappingValidationError(f"{tag}: string EtherNet/IP exige 'length' em bytes")
    length = _non_negative_int(tag, "length", addr.get("length", _default_length(e.datatype)))
    if length < 1:
        raise MappingValidationError(f"{tag}: length EtherNet/IP deve ser >= 1")
    slot: dict[str, Any] = {"offset": offset, "count": length, "unit": "byte"}
    bit = addr.get("bit")
    if bit is not None:
        if length not in (1, 2, 4):
            raise MappingValidationError(f"{tag}: 'bit' exige length 1, 2 ou 4 bytes")
        if isinstance(bit, bool) or not isinstance(bit, int) or not 0 <= bit < 8 * length:
            raise MappingValidationError(f"{tag}: bit fora de 0..{8 * length - 1}: {bit!r}")
        slot["bit"] = bit
    return (cls, inst, attr), slot


def _default_count(datatype: DataType | str, area: str) -> int:
    if area in MODBUS_BIT_AREAS:
        return 1
    return datatype.word_count if isinstance(datatype, DataType) else 1


def _default_length(datatype: DataType | str) -> int:
    if not isinstance(datatype, DataType):
        return 2
    return 1 if datatype in BYTE_TYPES else datatype.word_count * 2


def _non_negative_int(tag: str, key: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise MappingValidationError(f"{tag}: {key} EtherNet/IP inválido: {value!r}")
    return value


def _coalesce(spans: Sequence[_Span], limit: int) -> list[list[_Span]]:
    """Agrupa spans ordenados que se tocam ou se sobrepoem, respeitando o tamanho maximo."""
    groups: list[list[_Span]] = []
    current: list[_Span] = []
    start = end = 0
    for s in spans:
        if s.count > limit:
            raise MappingValidationError(f"{s.tag}: bloco de {s.count} acima do limite {limit}")
        if current and s.start <= end and max(end, s.end) - start <= limit:
            end = max(end, s.end)
            current.append(s)
            continue
        if current:
            groups.append(current)
        current, start, end = [s], s.start, s.end
    if current:
        groups.append(current)
    return groups


def _singles(spans: Sequence[_Span], limit: int) -> list[list[_Span]]:
    """Uma requisição por tag (opção block_reads: false). Mesmo limite de tamanho."""
    for s in spans:
        if s.count > limit:
            raise MappingValidationError(f"{s.tag}: bloco de {s.count} acima do limite {limit}")
    return [[s] for s in spans]


def _slot(span: _Span, start: int, unit: LayoutUnit) -> dict[str, Any]:
    slot: dict[str, Any] = {"offset": span.start - start, "count": span.count, "unit": unit}
    if span.bit is not None:
        slot["bit"] = span.bit
    return slot


def _block_from_group(area: str, group: Sequence[_Span], unit: LayoutUnit) -> ReadBlock:
    start = min(s.start for s in group)
    end = max(s.end for s in group)
    layout = {s.tag: _slot(s, start, unit) for s in group}
    return ReadBlock(
        block_id=f"{area}:{start}:{end - start}",
        area=area,
        address=start,
        count=end - start,
        tags=tuple(s.tag for s in group),
        meta={"layout": layout},
    )
