"""Cenarios do simulador WBF (Documento Mestre §25). Exatamente 9. Sem REFILL (LWF).

Os textos sao os que a UI mostra. O codigo interno (`BELTLOAD_LOW`) nunca e titulo.
"""

from __future__ import annotations

from enum import StrEnum

from forja.domain.errors import ConfigError


class Scenario(StrEnum):
    """Cenarios de demonstracao. Tudo que sai deles e SIMULATED."""

    NORMAL_OPERATION = "NORMAL_OPERATION"
    BELTLOAD_LOW = "BELTLOAD_LOW"
    RATE_LOW = "RATE_LOW"
    ENCODER_FAILURE = "ENCODER_FAILURE"
    SFT_FAILURE = "SFT_FAILURE"
    DRIVE_COMMAND_HIGH = "DRIVE_COMMAND_HIGH"
    INT_CHANNEL_DEGRADED = "INT_CHANNEL_DEGRADED"
    COMMUNICATION_FAILURE = "COMMUNICATION_FAILURE"
    STOP_NORMAL = "STOP_NORMAL"

    @property
    def title_pt(self) -> str:
        """Titulo curto para a UI."""
        return _TEXTS_PT[self][0]

    @property
    def description_pt(self) -> str:
        """Descricao simples do que o simulador faz neste cenario."""
        return _TEXTS_PT[self][1]


_TEXTS_PT: dict[Scenario, tuple[str, str]] = {
    Scenario.NORMAL_OPERATION: (
        "Operação normal",
        "Dosador em regime: vazão próxima do setpoint, material na correia e velocidade nas "
        "referências do perfil. Ruído pequeno.",
    ),
    Scenario.BELTLOAD_LOW: (
        "Pouco material na correia",
        "O material na correia cai até cerca de 45% da referência em cerca de 60 s. O controlador "
        "eleva o esforço do acionamento para manter a vazão, que cai pouco. Depois de persistir, "
        "o simulador liga o alarme com o código simulado 56.",
    ),
    Scenario.RATE_LOW: (
        "Vazão abaixo do setpoint",
        "A vazão fica de 15% a 25% abaixo do setpoint com o esforço do acionamento no teto. "
        "O controlador não consegue compensar.",
    ),
    Scenario.ENCODER_FAILURE: (
        "Falha na leitura de velocidade",
        "Após 20 s, a velocidade indicada vai a zero enquanto a máquina segue em operação e o "
        "esforço do acionamento continua acima de zero. Compatível com problema na cadeia de "
        "feedback de velocidade; a correia pode continuar girando.",
    ),
    Scenario.SFT_FAILURE: (
        "Falha na célula de pesagem (SFT)",
        "Após 30 s, o status bruto da SFT muda (valores simulados) e o peso líquido fica ruidoso. "
        "Depois de persistir, alarme ativo com o código simulado 8.",
    ),
    Scenario.DRIVE_COMMAND_HIGH: (
        "Esforço do acionamento alto",
        "O esforço do acionamento oscila entre 88% e 96% com a vazão próxima do setpoint.",
    ),
    Scenario.INT_CHANNEL_DEGRADED: (
        "Canal de integração degradado",
        "O uso do canal de integração cai de cerca de 95% para cerca de 40% em cerca de 60 s. "
        "Os demais sinais seguem normais. O limiar é do simulador, não do KCM.",
    ),
    Scenario.COMMUNICATION_FAILURE: (
        "Falha de comunicação",
        "Toda leitura falha por tempo esgotado. Não chega valor novo: a tentativa atual fica "
        "como sem comunicação e o último valor conhecido envelhece como valor antigo.",
    ),
    Scenario.STOP_NORMAL: (
        "Parada normal",
        "Máquina parada por entrada de parada (código simulado). Vazão, velocidade e esforço do "
        "acionamento em zero. O material permanece na correia. Parada não é falha.",
    ),
}

SCENARIO_COUNT = 9


def scenario_from_text(value: object) -> Scenario:
    """Converte o valor de `communication.options.scenario` em Scenario. Erro em portugues."""
    if isinstance(value, Scenario):
        return value
    if isinstance(value, str):
        try:
            return Scenario(value.strip().upper())
        except ValueError:
            pass
    names = ", ".join(s.value for s in Scenario)
    raise ConfigError(f"cenário do simulador desconhecido: {value!r}. Válidos: {names}")
