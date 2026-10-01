"""Tags semanticas independentes de protocolo (spec §21, §50; Documento Mestre §15.2).

Nem toda maquina expoe todas. O mapping diz quais existem.
Textos em portugues sao os que a UI mostra; o codigo tecnico fica em 'Detalhes tecnicos'.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class TagKind(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    DISCRETE = "DISCRETE"
    STATUS_RAW = "STATUS_RAW"


class SemanticTag(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    label_pt: str
    unit: str
    kind: TagKind
    explanation_pt: str
    decimals: int = 1


_TAGS: tuple[SemanticTag, ...] = (
    SemanticTag(
        code="machine_state",
        label_pt="Estado da máquina",
        unit="",
        kind=TagKind.DISCRETE,
        explanation_pt="Estado informado pelo KCM (em operação, parado, alarme).",
        decimals=0,
    ),
    SemanticTag(
        code="setpoint",
        label_pt="Setpoint",
        unit="kg/h",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Vazão desejada, definida pela operação ou pelo sistema de controle.",
        decimals=0,
    ),
    SemanticTag(
        code="mass_flow",
        label_pt="Vazão",
        unit="kg/h",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Quantidade de material dosada por unidade de tempo.",
        decimals=0,
    ),
    SemanticTag(
        code="drive_command",
        label_pt="Esforço do acionamento",
        unit="%",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Quanto o controlador está solicitando ao acionamento.",
        decimals=1,
    ),
    SemanticTag(
        code="rpm",
        label_pt="Velocidade indicada",
        unit="rpm",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Velocidade indicada pelo sistema de feedback (encoder ou sensor).",
        decimals=0,
    ),
    SemanticTag(
        code="belt_load",
        label_pt="Material na correia",
        unit="kg/m",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Quantidade de material sobre a correia por unidade de comprimento.",
        decimals=2,
    ),
    SemanticTag(
        code="vol_belt_load",
        label_pt="Carga volumétrica",
        unit="kg/m",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Carga de referência da correia em modo volumétrico.",
        decimals=2,
    ),
    SemanticTag(
        code="net_weight",
        label_pt="Peso líquido",
        unit="kg",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Peso medido pela balança descontada a tara.",
        decimals=3,
    ),
    SemanticTag(
        code="gross_weight",
        label_pt="Peso bruto",
        unit="kg",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Peso medido pela balança sem descontar a tara.",
        decimals=3,
    ),
    SemanticTag(
        code="alarm_code",
        label_pt="Código de alarme",
        unit="",
        kind=TagKind.DISCRETE,
        explanation_pt="Código numérico do alarme ativo no KCM. O significado depende da aplicação e da versão.",
        decimals=0,
    ),
    SemanticTag(
        code="alarm_active",
        label_pt="Alarme ativo",
        unit="",
        kind=TagKind.DISCRETE,
        explanation_pt="Existe alarme ativo no KCM.",
        decimals=0,
    ),
    SemanticTag(
        code="stop_by",
        label_pt="Motivo da parada",
        unit="",
        kind=TagKind.STATUS_RAW,
        explanation_pt="Origem da parada informada pelo KCM. Parada não significa falha.",
        decimals=0,
    ),
    SemanticTag(
        code="sft_status",
        label_pt="Status SFT",
        unit="",
        kind=TagKind.STATUS_RAW,
        explanation_pt="Status bruto da célula de pesagem SFT. Guardado como veio; sem decodificação sem fonte.",
        decimals=0,
    ),
    SemanticTag(
        code="sft_list",
        label_pt="Lista de SFT",
        unit="",
        kind=TagKind.STATUS_RAW,
        explanation_pt="Identificação das células SFT presentes.",
        decimals=0,
    ),
    SemanticTag(
        code="mdu_status",
        label_pt="Status MDU",
        unit="",
        kind=TagKind.STATUS_RAW,
        explanation_pt="Status bruto do módulo de acionamento MDU. Guardado como veio; sem decodificação sem fonte.",
        decimals=0,
    ),
    SemanticTag(
        code="int_channel_pct",
        label_pt="Canal de integração",
        unit="%",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Uso do canal de integração da pesagem.",
        decimals=1,
    ),
    SemanticTag(
        code="control_mode",
        label_pt="Modo de controle",
        unit="",
        kind=TagKind.DISCRETE,
        explanation_pt="Gravimétrico ou volumétrico.",
        decimals=0,
    ),
    SemanticTag(
        code="tare",
        label_pt="Tara",
        unit="kg",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Valor de tara registrado no KCM.",
        decimals=4,
    ),
    SemanticTag(
        code="span",
        label_pt="Span",
        unit="",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Valor de span da calibração registrado no KCM.",
        decimals=4,
    ),
    SemanticTag(
        code="cal_correlation",
        label_pt="Correlação de calibração",
        unit="%",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Correlação informada na última calibração.",
        decimals=1,
    ),
    SemanticTag(
        code="motor_load_pct",
        label_pt="Carga do motor",
        unit="%",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Carga do motor informada pelo acionamento, quando exposta.",
        decimals=1,
    ),
    SemanticTag(
        code="kcm_temp",
        label_pt="Temperatura do KCM",
        unit="°C",
        kind=TagKind.CONTINUOUS,
        explanation_pt="Temperatura interna do controlador, quando exposta.",
        decimals=1,
    ),
)

TAGS: dict[str, SemanticTag] = {t.code: t for t in _TAGS}
TAG_CODES: tuple[str, ...] = tuple(TAGS.keys())


def get_tag(code: str) -> SemanticTag:
    try:
        return TAGS[code]
    except KeyError as exc:
        raise KeyError(f"tag semântica desconhecida: {code!r}") from exc


def is_known_tag(code: str) -> bool:
    return code in TAGS
