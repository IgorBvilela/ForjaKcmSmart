"""Biblioteca de diagnóstico.

Para cada tipo de evento, a biblioteca entrega três coisas, nesta ordem:

    EVIDÊNCIAS   o que foi observado, com valor, instante e qualidade
    HIPÓTESES    o que PODE explicar, cada uma com o que a confirma ou descarta
    VERIFICAÇÕES o que uma pessoa faz em campo, na ordem, para separar as hipóteses

REGRAS DA CASA
--------------
1. A biblioteca não conclui causa. Ela ordena a investigação.
2. `rank` é ORDEM DE VERIFICAÇÃO, não probabilidade medida. A ordem combina
   custo de verificar (barato e não invasivo primeiro) com o que já foi visto
   em campo. Não há estatística por trás, e o campo `ranking_basis` diz isso.
3. Toda verificação é feita POR UMA PESSOA. Este sistema é read-only: ele não
   escreve no KCM, não move parâmetro e não comanda nada. As verificações são
   instruções, nunca ações automáticas.
4. Hipótese descartada pelos próprios dados aparece como descartada, com o
   dado que a descartou.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from forja.events.models import EventType


class Rank(str, Enum):
    """Ordem sugerida de investigação. NÃO é probabilidade."""
    FIRST = "verificar_primeiro"
    NEXT = "verificar_depois"
    LAST = "verificar_por_ultimo"


@dataclass(frozen=True)
class Hypothesis:
    id: str
    name: str
    statement: str            # o que seria o caso, se esta hipótese valesse
    rationale: str            # por que está na lista
    discriminator: str        # o que CONFIRMA ou DESCARTA esta hipótese
    rank: Rank = Rank.NEXT
    source: str = "opinião técnica da Forja"
    ranking_basis: str = ("ordenado por custo de verificação e pelo que já foi observado "
                          "em campo; não é probabilidade calculada")


@dataclass(frozen=True)
class Check:
    order: int
    action: str               # o que fazer
    expected: str             # o que o resultado significa
    invasive: bool = False    # exige abrir, desconectar ou mexer em fiação
    requires_stop: bool = False
    safety_note: str = ""
    tool: str = ""


@dataclass(frozen=True)
class DiagnosticEntry:
    event_type: EventType
    question: str             # a pergunta que o diagnóstico responde
    hypotheses: list[Hypothesis]
    checks: list[Check]
    caveats: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SPEED_FEEDBACK_ANOMALY — o caminho do sinal de velocidade
#
# Trilha de investigação alinhada ao caminho percorrido no atendimento GTEX
# (ver knowledge/cases/GTEX-PHA-KCM-SPEED-001.yaml). Ali o caminho foi
# segmentado ponto a ponto, e o defeito apareceu no cabo/conector, não na
# eletrônica. A lição registrada no caso é justamente não trocar o encoder
# antes de segmentar o caminho do sinal.
# ---------------------------------------------------------------------------
_SPEED = DiagnosticEntry(
    event_type=EventType.SPEED_FEEDBACK_ANOMALY,
    question="o motor está girando de verdade, e o sinal de velocidade está chegando ao KCM?",
    hypotheses=[
        Hypothesis(
            id="H-SPEED-CONFIRM",
            name="Confirmar primeiro se o eixo gira",
            statement="o motor pode estar realmente parado, e a RPM zero estar correta",
            rationale="antes de caçar defeito de sinal, é preciso saber se o sintoma é falso: "
                      "RPM zero com eixo parado não é anomalia de realimentação",
            discriminator="observação visual direta do eixo ou da correia com a máquina em RUN",
            rank=Rank.FIRST,
        ),
        Hypothesis(
            id="H-SPEED-CABLE",
            name="Cabo ou conector do sinal de velocidade",
            statement="o sinal é gerado na origem mas não chega à entrada do controlador",
            rationale="rompimento e mau contato reproduzem exatamente o sintoma de falha "
                      "eletrônica, e é o que foi encontrado na ocorrência registrada na base",
            discriminator="medir continuidade trecho a trecho e comparar o sinal antes e "
                          "depois de cada conector: presente na origem e ausente na chegada "
                          "isola o trecho",
            rank=Rank.FIRST,
            source="caso GTEX-PHA-KCM-SPEED-001 (observação de campo)",
        ),
        Hypothesis(
            id="H-SPEED-GAP",
            name="Gap ou alinhamento do pickup",
            statement="a distância entre o pickup e a roda dentada saiu da faixa e o pulso não forma",
            rationale="ajuste mecânico simples, barato de verificar e sensível a vibração e sujeira",
            discriminator="medir a distância física e verificar se há pulso na saída do pickup "
                          "com o eixo girando",
            rank=Rank.FIRST,
        ),
        Hypothesis(
            id="H-SPEED-SUPPLY",
            name="Alimentação do encoder",
            statement="o encoder não está sendo alimentado corretamente e por isso não gera pulso",
            rationale="medição rápida, não invasiva, e descarta um bloco inteiro do caminho",
            discriminator="medir a tensão de alimentação no próprio encoder, com a máquina energizada",
            rank=Rank.NEXT,
            source="caso GTEX-PHA-KCM-SPEED-001 (medição de 4,9 V registrada no atendimento)",
        ),
        Hypothesis(
            id="H-SPEED-INTERFACE",
            name="Interface intermediária (SIB ou equivalente) e entrada do controlador",
            statement="o sinal chega até a interface mas não é entregue à entrada que o KCM lê",
            rationale="a presença e o modelo da interface nesta máquina ainda não estão confirmados "
                      "na ficha do equipamento",
            discriminator="medir o sinal na entrada e na saída da interface: presente na entrada "
                          "e ausente na saída isola o componente",
            rank=Rank.NEXT,
            invasiveness_note := None or "",
        ) if False else Hypothesis(
            id="H-SPEED-INTERFACE",
            name="Interface intermediária (SIB ou equivalente) e entrada do controlador",
            statement="o sinal chega até a interface mas não é entregue à entrada que o KCM lê",
            rationale="a presença e o modelo da interface nesta máquina ainda não estão confirmados "
                      "na ficha do equipamento",
            discriminator="medir o sinal na entrada e na saída da interface: presente na entrada "
                          "e ausente na saída isola o componente",
            rank=Rank.NEXT,
        ),
        Hypothesis(
            id="H-SPEED-PARAM",
            name="Parâmetro de contagem (PICK UP TEETH) ou configuração",
            statement="o sinal chega, mas a configuração faz o controlador calcular zero ou valor errado",
            rationale="defeito sem peça defeituosa; costuma aparecer depois de troca de placa, "
                      "restauração de configuração ou substituição de componente por outro modelo",
            discriminator="comparar o parâmetro configurado com a roda dentada real e com a "
                          "frequência medida; registrar o valor AS FOUND antes de alterar",
            rank=Rank.NEXT,
        ),
        Hypothesis(
            id="H-SPEED-ENCODER",
            name="Encoder com defeito",
            statement="o transdutor em si parou de gerar sinal",
            rationale="é a conclusão só depois que o caminho do sinal foi segmentado; trocar antes "
                      "disso foi registrado como erro a evitar na base de casos",
            discriminator="com alimentação correta, gap correto e eixo girando, ausência de "
                          "frequência na própria saída do encoder",
            rank=Rank.LAST,
            source="caso GTEX-PHA-KCM-SPEED-001 (lição registrada)",
        ),
    ],
    checks=[
        Check(order=1, action="observar se o eixo ou a correia se movem com a máquina em RUN",
              expected="se não há movimento, o sintoma é outro: investigar acionamento, não realimentação",
              safety_note="observar a distância; não abrir proteção com a máquina energizada"),
        Check(order=2, action="registrar os valores AS FOUND do KCM antes de mexer em qualquer coisa",
              expected="fotografar ou anotar tela, parâmetros e códigos ativos",
              tool="câmera; formulário de atendimento"),
        Check(order=3, action="medir a tensão de alimentação no encoder",
              expected="fora da faixa esperada aponta para alimentação; dentro da faixa descarta esse bloco",
              tool="multímetro"),
        Check(order=4, action="medir a frequência na saída do pickup com o eixo girando",
              expected="sem frequência na origem: pickup, gap ou encoder. Com frequência: o problema "
                       "está adiante, no caminho até o controlador",
              tool="frequencímetro ou osciloscópio"),
        Check(order=5, action="verificar a distância e o alinhamento do pickup em relação à roda dentada",
              expected="fora da faixa mecânica explica ausência de pulso sem componente queimado",
              invasive=True, requires_stop=True,
              safety_note="com a máquina parada e bloqueada", tool="lâmina calibradora"),
        Check(order=6, action="medir continuidade do cabo trecho a trecho, e refazer a inspeção "
                              "dos conectores das duas pontas",
              expected="descontinuidade ou resistência fora do esperado isola o trecho rompido",
              invasive=True, requires_stop=True,
              safety_note="com a máquina parada e desenergizada", tool="multímetro"),
        Check(order=7, action="comparar o sinal na entrada e na saída de cada interface intermediária",
              expected="presente na entrada e ausente na saída isola o componente",
              invasive=True, tool="osciloscópio"),
        Check(order=8, action="conferir o parâmetro de contagem contra a roda dentada real e "
                              "contra a frequência medida",
              expected="divergência explica leitura errada sem defeito físico",
              safety_note="anotar o valor encontrado antes de qualquer alteração"),
    ],
    caveats=[
        "o nome do evento descreve o sintoma (realimentação em zero), não a causa",
        "calibrar a máquina antes de resolver o problema físico esconde o defeito em vez de corrigir",
    ],
)


# ---------------------------------------------------------------------------
# Demais entradas
# ---------------------------------------------------------------------------
_COMM = DiagnosticEntry(
    event_type=EventType.COMMUNICATION_LOSS,
    question="por que a tentativa de leitura está falhando agora?",
    hypotheses=[
        Hypothesis(id="H-COMM-LINK", name="Enlace físico de rede",
                   statement="cabo, porta ou switch entre o Edge e o controlador",
                   rationale="é o ponto mais comum e o mais barato de verificar",
                   discriminator="teste de alcance na rede e verificação de link nas portas",
                   rank=Rank.FIRST),
        Hypothesis(id="H-COMM-HOST", name="Placa de comunicação do controlador",
                   statement="a placa host parou de responder ou foi reiniciada",
                   rationale="a ficha do equipamento registra placa host presente, com protocolo "
                             "ainda não confirmado",
                   discriminator="observar os LEDs da placa e se a resposta volta após religar",
                   rank=Rank.NEXT),
        Hypothesis(id="H-COMM-CONFIG", name="Endereço, porta ou protocolo incorretos no Edge",
                   statement="o Edge está falando no lugar errado ou na língua errada",
                   rationale="o protocolo do equipamento está UNKNOWN na ficha até a descoberta em campo",
                   discriminator="conferir a ficha do equipamento contra o que a planta informa",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="verificar se o evento DATA_STALE acompanha este",
              expected="os dois juntos confirmam que a leitura falhou E que a tela mostra valor antigo"),
        Check(order=2, action="conferir link físico e alcance de rede até o endereço configurado",
              expected="sem alcance: problema de rede, não do controlador", tool="ping; teste de link"),
        Check(order=3, action="observar os LEDs da placa de comunicação do controlador",
              expected="sem atividade indica placa ou alimentação"),
    ],
    caveats=["enquanto a comunicação estiver perdida, as demais regras ficam caladas de propósito: "
             "o sistema não gera diagnóstico a partir de número velho"],
)

_STALE = DiagnosticEntry(
    event_type=EventType.DATA_STALE,
    question="de quando é o número que está na tela?",
    hypotheses=[
        Hypothesis(id="H-STALE-COMM", name="Consequência de falha de leitura",
                   statement="os valores congelaram porque as leituras pararam de chegar",
                   rationale="é a origem mais comum; o par COMMUNICATION_LOSS costuma estar aberto",
                   discriminator="existe evento COMMUNICATION_LOSS aberto no mesmo período?",
                   rank=Rank.FIRST),
        Hypothesis(id="H-STALE-PERIOD", name="Período de varredura maior que o esperado",
                   statement="a tag é lida com período longo e o valor é antigo por configuração",
                   rationale="tags de diagnóstico têm período maior que as de processo",
                   discriminator="comparar a idade do valor com o período configurado para a tag",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="ler a idade do valor no campo age_s da amostra",
              expected="idade próxima do período configurado é normal; muito acima indica falha"),
        Check(order=2, action="verificar se há COMMUNICATION_LOSS aberto no mesmo instante",
              expected="se sim, a causa é a falha de leitura e não a configuração"),
    ],
    caveats=["valor STALE nunca é apresentado como leitura atual e não dispara as demais regras"],
)

_ALARM = DiagnosticEntry(
    event_type=EventType.KCM_ALARM,
    question="o que o controlador declarou, e o que isso significa NESTA máquina?",
    hypotheses=[
        Hypothesis(id="H-ALARM-SCOPE", name="Confirmar o significado do código nesta máquina",
                   statement="o número pode significar outra coisa nesta aplicação ou configuração",
                   rationale="a tabela de códigos depende da aplicação e do arquivo de configuração; "
                             "o catálogo do sistema registra escopo e fonte de cada entrada",
                   discriminator="ler o texto do alarme na própria tela do controlador e comparar "
                                 "com o que o catálogo registra",
                   rank=Rank.FIRST),
        Hypothesis(id="H-ALARM-CONTEXT", name="Ler o alarme junto com o comportamento das tags",
                   statement="o código sozinho não separa causa; o contexto ao redor separa",
                   rationale="o mesmo código aparece em condições diferentes",
                   discriminator="comparar o antes e o depois capturados no contexto do evento",
                   rank=Rank.FIRST),
    ],
    checks=[
        Check(order=1, action="ler o texto do alarme na tela do KCM e fotografar",
              expected="confirma ou corrige a entrada do catálogo para esta máquina", tool="câmera"),
        Check(order=2, action="comparar o instante do alarme com o contexto anterior do evento",
              expected="mostra o que mudou antes do controlador declarar"),
    ],
    caveats=["nenhuma entrada do catálogo de alarmes vale para todo KCM: cada uma declara "
             "aplicação, modelo, escopo e fonte",
             "a recíproca não vale: a mesma condição física pode emitir outro código, ou nenhum"],
)

_SFT = DiagnosticEntry(
    event_type=EventType.SFT_NOT_RESPONDING,
    question="o transdutor de pesagem está respondendo ao controlador?",
    hypotheses=[
        Hypothesis(id="H-SFT-CABLE", name="Cabo ou conector do SFT",
                   statement="a ligação física com o transdutor foi interrompida",
                   rationale="ambiente com pó e sal favorece corrosão e mau contato; foi o que "
                             "apareceu na ocorrência registrada na base",
                   discriminator="continuidade do cabo e inspeção do conector",
                   rank=Rank.FIRST, source="caso GTEX-PHA-KCM-SPEED-001"),
        Hypothesis(id="H-SFT-ADDRESS", name="Endereço do SFT",
                   statement="o endereço esperado não corresponde ao configurado",
                   rationale="verificação de configuração, sem intervenção física",
                   discriminator="comparar o endereço configurado com a lista mostrada na tela",
                   rank=Rank.NEXT),
        Hypothesis(id="H-SFT-DEVICE", name="Transdutor com defeito",
                   statement="o SFT em si parou de responder",
                   rationale="conclusão depois de descartar cabo, conector e endereço",
                   discriminator="resposta ausente com cabo e endereço confirmados",
                   rank=Rank.LAST),
    ],
    checks=[
        Check(order=1, action="registrar o status cru mostrado na tela, sem interpretar",
              expected="o status hexadecimal é guardado como texto e comparado ao longo do tempo"),
        Check(order=2, action="inspecionar conector e cabo do transdutor",
              expected="corrosão ou rompimento explica a ausência de resposta",
              invasive=True, requires_stop=True, safety_note="com a máquina parada e desenergizada"),
        Check(order=3, action="conferir o endereço configurado contra a lista de SFTs da tela",
              expected="divergência explica ausência sem defeito de hardware"),
    ],
    caveats=["status hexadecimal de SFT e MDU é guardado cru: o sistema não decodifica "
             "sem tabela confirmada do fabricante"],
)

_BELT = DiagnosticEntry(
    event_type=EventType.BELT_LOAD_LOW,
    question="por que está entrando menos material na correia do que o esperado?",
    hypotheses=[
        Hypothesis(id="H-BELT-SUPPLY", name="Alimentação a montante",
                   statement="está chegando menos material do que a correia deveria receber",
                   rationale="verificação visual, sem ferramenta",
                   discriminator="observar o nível e o fluxo na entrada",
                   rank=Rank.FIRST),
        Hypothesis(id="H-BELT-FLOW", name="Obstrução ou formação de abóbada",
                   statement="o material trava antes de chegar à correia",
                   rationale="comum em pó com umidade; a ficha registra pó, sal e umidade elevada",
                   discriminator="inspeção visual da entrada e do fluxo",
                   rank=Rank.FIRST),
        Hypothesis(id="H-BELT-WEIGH", name="Pesagem deslocada (tara, span ou sujeira)",
                   statement="há material, mas a medição indica menos do que existe",
                   rationale="separa problema de processo de problema de medição",
                   discriminator="comparar tara e span com os valores de referência e inspecionar "
                                 "acúmulo sobre a correia e na região pesada",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="observar a entrada de material com a máquina operando",
              expected="falta de material na entrada explica sem envolver medição"),
        Check(order=2, action="comparar belt load medido com a referência volumétrica registrada",
              expected="divergência grande com entrada normal aponta para pesagem"),
        Check(order=3, action="inspecionar acúmulo de material na correia e na região pesada",
              expected="acúmulo desloca a medição", invasive=True, requires_stop=True,
              safety_note="com a máquina parada e bloqueada"),
    ],
)

_DRIVE = DiagnosticEntry(
    event_type=EventType.DRIVE_COMMAND_SATURATED,
    question="por que o controlador precisa de tanto acionamento para manter a vazão?",
    hypotheses=[
        Hypothesis(id="H-DRIVE-LOAD", name="Carga na correia abaixo do necessário",
                   statement="falta material, e o controlador compensa acelerando",
                   rationale="é a explicação mais direta e visível nos dados",
                   discriminator="belt load baixo junto com drive command alto",
                   rank=Rank.FIRST),
        Hypothesis(id="H-DRIVE-MECH", name="Resistência mecânica",
                   statement="a correia ou o acionamento estão exigindo mais esforço",
                   rationale="desgaste, desalinhamento ou tensão incorreta",
                   discriminator="comparar motor load com o histórico da mesma receita",
                   rank=Rank.NEXT),
        Hypothesis(id="H-DRIVE-SETPOINT", name="Setpoint acima da capacidade",
                   statement="a máquina está sendo pedida além do que entrega",
                   rationale="verificação de operação, sem intervenção",
                   discriminator="comparar o setpoint com a capacidade registrada para a receita",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="comparar drive command, belt load e vazão no mesmo período",
              expected="drive alto com belt load baixo aponta alimentação"),
        Check(order=2, action="comparar motor load com o histórico da mesma receita",
              expected="aumento sustentado aponta resistência mecânica"),
    ],
)

_RATE = DiagnosticEntry(
    event_type=EventType.RATE_DEVIATION,
    question="a vazão está fora do setpoint por processo ou por medição?",
    hypotheses=[
        Hypothesis(id="H-RATE-TRANSIENT", name="Transitório normal",
                   statement="partida, troca de receita ou variação momentânea",
                   rationale="descartar primeiro o que não é defeito",
                   discriminator="o desvio se resolve sozinho em poucos minutos?",
                   rank=Rank.FIRST),
        Hypothesis(id="H-RATE-SUPPLY", name="Alimentação irregular",
                   statement="a entrada de material oscila",
                   rationale="aparece junto com oscilação de belt load",
                   discriminator="observar a variação de belt load no mesmo período",
                   rank=Rank.NEXT),
        Hypothesis(id="H-RATE-CALIB", name="Calibração deslocada",
                   statement="a máquina entrega o correto mas indica outro valor",
                   rationale="separa processo de medição",
                   discriminator="comparar contra pesagem de referência externa",
                   rank=Rank.LAST),
    ],
    checks=[
        Check(order=1, action="acompanhar o desvio por alguns minutos antes de intervir",
              expected="transitório se resolve; desvio sustentado não"),
        Check(order=2, action="comparar vazão indicada com pesagem de referência",
              expected="divergência confirma medição e não processo",
              tool="balança de referência"),
    ],
    caveats=["calibrar sem antes descartar problema físico esconde o defeito"],
)

_INT = DiagnosticEntry(
    event_type=EventType.INT_CHANNEL_DEGRADED,
    question="o canal interno está degradando de forma progressiva?",
    hypotheses=[
        Hypothesis(id="H-INT-TREND", name="Degradação progressiva",
                   statement="o valor cai de forma lenta e contínua ao longo de horas",
                   rationale="tendência é mais informativa que o valor isolado",
                   discriminator="comparar a série das últimas horas com a dos dias anteriores",
                   rank=Rank.FIRST),
        Hypothesis(id="H-INT-ENV", name="Condição ambiental",
                   statement="temperatura, pó ou umidade afetando a eletrônica",
                   rationale="a ficha registra pó alto, sal e umidade elevada",
                   discriminator="correlacionar com a temperatura registrada do controlador",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="observar a série do canal nas últimas horas",
              expected="queda contínua indica degradação; oscilação indica ruído"),
        Check(order=2, action="comparar com a temperatura do controlador no mesmo período",
              expected="correlação aponta condição ambiental"),
    ],
)

_STOP = DiagnosticEntry(
    event_type=EventType.MACHINE_STOPPED,
    question="esta parada é normal, solicitada, de proteção ou de falha?",
    hypotheses=[
        Hypothesis(id="H-STOP-CLASS", name="Ler a classificação antes de tratar como problema",
                   statement="a parada pode ser fim de procedimento, e não defeito",
                   rationale="calibração, tara e esvaziamento param a máquina normalmente; "
                             "tratar isso como falha gera alarme falso e desgasta o operador",
                   discriminator="a classe do STOP BY registrada no contexto do evento",
                   rank=Rank.FIRST),
        Hypothesis(id="H-STOP-PROTECT", name="Proteção ou intertravamento atuou",
                   statement="uma condição externa impediu a operação",
                   rationale="exige olhar o que está a montante ou a jusante",
                   discriminator="STOP BY classificado como proteção",
                   rank=Rank.NEXT),
    ],
    checks=[
        Check(order=1, action="ler a classe do STOP BY no contexto do evento",
              expected="normal ou solicitada: registrar e seguir. Proteção ou falha: investigar"),
        Check(order=2, action="para parada de falha, verificar o código de alarme do mesmo instante",
              expected="o alarme ativo no momento da parada aponta o caminho"),
    ],
    caveats=["STOP não é falha por padrão: a classificação é decisão de arquitetura da Forja, "
             "registrada no domínio, e não vem do manual do controlador"],
)


LIBRARY: dict[EventType, DiagnosticEntry] = {
    e.event_type: e for e in [_SPEED, _COMM, _STALE, _ALARM, _SFT, _BELT, _DRIVE, _RATE, _INT, _STOP]
}


def entry_for(event_type: EventType | str) -> Optional[DiagnosticEntry]:
    if isinstance(event_type, str):
        try:
            event_type = EventType(event_type)
        except ValueError:
            return None
    return LIBRARY.get(event_type)


def coverage() -> dict[str, Any]:
    """Quais tipos de evento têm entrada na biblioteca e quais ainda não têm."""
    covered = sorted(t.value for t in LIBRARY)
    missing = sorted(t.value for t in EventType if t not in LIBRARY)
    return {"covered": covered, "missing": missing,
            "total_event_types": len(list(EventType)), "covered_count": len(covered)}
