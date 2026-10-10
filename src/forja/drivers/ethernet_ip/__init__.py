"""Driver EtherNet/IP somente leitura (mensagem explícita, sem conexão de I/O)."""

from forja.drivers.ethernet_ip.driver import (
    EXPERIMENTAL_NOTE_PT,
    EipSettings,
    EthernetIpDriver,
    eip_settings,
)

__all__ = ["EXPERIMENTAL_NOTE_PT", "EipSettings", "EthernetIpDriver", "eip_settings"]
