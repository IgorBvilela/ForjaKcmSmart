"""Relatório de comissionamento em CSV (dialeto brasileiro: ';', vírgula decimal, BOM).

Primeiro o cabeçalho da visita (uma linha "campo;valor" por informação), depois a tabela das
conferências com instante, variável, endereço, valor Forja, valor no KCM, diferença, qualidade,
resultado e observação. Nada é arredondado além do que foi registrado.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Sequence

from forja.domain import TAGS, CommissioningCheck, CommissioningSession
from forja.reports.csv_export import BOM, CsvDialect, fmt_value, iso_utc, local_text

CHECK_HEADER: tuple[str, ...] = (
    "data_hora_utc",
    "data_hora_planta",
    "tag",
    "variavel",
    "unidade",
    "endereco",
    "valor_forja",
    "bruto_forja_hex",
    "qualidade_forja",
    "valor_kcm",
    "texto_kcm",
    "diferenca",
    "resultado",
    "observacao",
    "tecnico",
)


def commissioning_csv(
    session: CommissioningSession, checks: Sequence[CommissioningCheck], *, timezone: str
) -> str:
    buf = io.StringIO()
    buf.write(BOM)
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    h = session.header
    for label, value in (
        ("Relatório", "Comissionamento / validação em campo (Forja KCM Intelligence)"),
        ("Equipamento", session.equipment_id),
        ("Sessão", session.id),
        ("Situação", session.status.label_pt),
        ("Data da visita", h.visit_date.isoformat()),
        ("Técnico", h.technician),
        ("Autorizado por", h.authorized_by),
        ("Protocolo encontrado", h.protocol_found),
        ("Versão do software do KCM", h.kcm_software_version),
        ("Interface Host/Anybus", h.host_interface),
        ("IP", h.ip),
        ("Máscara", h.subnet_mask),
        ("Gateway", h.gateway),
        ("Mapping", f"{h.mapping_id} v{h.mapping_version}" if h.mapping_version else h.mapping_id),
        ("Contadores Host antes", h.host_counters_before),
        ("Contadores Host depois", h.host_counters_after),
        ("Observações", h.notes_pt),
        ("Conclusão", session.conclusion_pt),
        ("Aberta em (UTC)", iso_utc(session.created_at_utc)),
        ("Atualizada em (UTC)", iso_utc(session.updated_at_utc)),
    ):
        writer.writerow((label, value))
    writer.writerow(())
    writer.writerow(CHECK_HEADER)
    for c in checks:
        meta = TAGS.get(c.tag)
        writer.writerow(
            (
                iso_utc(c.ts_utc),
                local_text(c.ts_utc, timezone),
                c.tag,
                c.label_pt or (meta.label_pt if meta else c.tag),
                c.unit or (meta.unit if meta else ""),
                c.address_text,
                fmt_value(c.forja_value, CsvDialect.BR),
                c.forja_raw_hex or "",
                c.forja_quality.label_pt if c.forja_quality else "",
                fmt_value(c.kcm_value, CsvDialect.BR),
                c.kcm_text,
                fmt_value(c.difference, CsvDialect.BR),
                c.result.label_pt,
                c.note_pt,
                c.technician,
            )
        )
    return buf.getvalue()


__all__ = ["CHECK_HEADER", "commissioning_csv"]
