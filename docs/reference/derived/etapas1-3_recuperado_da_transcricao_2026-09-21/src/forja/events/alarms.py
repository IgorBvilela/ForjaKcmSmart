"""Catálogo de alarmes do KCM — por CHAVE COMPOSTA.

POR QUE CHAVE COMPOSTA
----------------------
"Alarme 56 = BELTLOAD LOW" é uma afirmação falsa se dita sozinha. O que
temos é mais estreito e mais honesto:

    na aplicação WBF, num KCM configurado como o da GTEX,
    o código 56 foi OBSERVADO NA TELA como BELTLOAD LOW.

Trocar a aplicação, a geração do controlador ou o arquivo de configuração
pode mudar a tabela de códigos. Por isso a chave é
(aplicação, modelo do controlador, código) e nunca o código sozinho.

O QUE ESTE MÓDULO NÃO FAZ
-------------------------
Não afirma causa. Uma entrada diz como o código apareceu e de onde veio a
informação; a causa é trabalho da biblioteca de diagnóstico, e mesmo lá
sai como hipótese com verificações.

Também não vale a recíproca: se o código 08 foi observado numa condição de
SFT, isso NÃO significa que toda condição de SFT produz o código 08, nem
que o código 08 só aparece por SFT. Cada entrada declara isso no campo
`reverse_warning`, e nenhuma regra do motor depende da recíproca.

NÍVEL DE EVIDÊNCIA DE CADA ENTRADA
----------------------------------
Nenhuma entrada deste catálogo está hoje em MANUFACTURER_DOC. Os documentos
que temos (contexto mestre, suplemento técnico, guia PT-BR de alarmes) têm
seção, mas não têm revisão identificada e não são, até onde sabemos,
material do fabricante. Pela regra de promoção em forja.domain.evidence,
isso os mantém em TECHNICAL_OPINION — com a referência parcial anexada, para
que se saiba exatamente o que falta confirmar.

Essa classificação é para baixo de propósito. Chamar de "documentado pelo
fabricante" o que não pode ser conferido numa revisão específica daria ao
técnico uma confiança que a informação não sustenta.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from forja.domain.evidence import (DocReference, EvidenceLevel, NO_REFERENCE,
                                   describe, validate_evidence)
from forja.domain.models import Application

from .models import Severity

ANY_MODEL = "ANY"


@dataclass(frozen=True)
class AlarmKey:
    """Identidade de um alarme. O código sozinho NÃO identifica nada."""
    application: Application
    controller_model: str
    code: int

    def __str__(self) -> str:
        return f"{self.application.value}/{self.controller_model}/{self.code:02d}"


@dataclass(frozen=True)
class AlarmDefinition:
    key: AlarmKey
    name: str                     # como apareceu/consta na tela
    meaning: str                  # o que o texto significa, em português simples
    severity: Severity
    evidence: EvidenceLevel
    scope: str                    # frase que delimita a validade desta entrada
    source: str                   # documento ou observação de origem
    doc_ref: DocReference = field(default_factory=lambda: NO_REFERENCE)
    observed_on: str = ""         # equipamento onde foi observado, quando aplicável
    reverse_warning: str = ""     # por que a recíproca não vale
    universal: bool = False       # sempre False: nenhuma entrada vale para todo KCM

    def __post_init__(self) -> None:
        validate_evidence(self.evidence, self.doc_ref, what=f"alarme {self.key}")

    @property
    def is_known(self) -> bool:
        return self.evidence is not EvidenceLevel.UNKNOWN

    def evidence_block(self) -> dict:
        return describe(self.evidence, self.doc_ref)

    def describe(self) -> str:
        return f"{self.name} ({self.key}) — {self.meaning} [{self.evidence.value}: {self.source}]"


# ---------------------------------------------------------------------------
# Entradas. Toda entrada nasce com escopo, fonte e nível de evidência.
# ---------------------------------------------------------------------------
GTEX_WBF = "GTEX / PHA / Dosador Pó Base (KCM WBF)"

# Referências que TEMOS, com o que falta para promover cada uma. Manter isso
# explícito é o que transforma "falta documentação" numa lista de tarefas em
# vez de uma sensação.
_REF_CONTEXTO = DocReference(
    document="contexto mestre do projeto", section="§9",
    note="falta a revisão; não é documento do fabricante. Sem isso a entrada "
         "permanece em TECHNICAL_OPINION.")
_REF_SUPLEMENTO_29 = DocReference(
    document="suplemento técnico do projeto", section="§29–32",
    note="falta a revisão; confirmar contra a tabela de alarmes do arquivo de "
         "configuração desta máquina.")
_REF_GUIA_ALARMES = DocReference(
    document="guia PT-BR de alarmes", section="§44",
    note="falta a revisão e a confirmação de que corresponde à geração deste KCM.")
_REF_FOTO_TELA = DocReference(
    document="documento de campo 4 — fotos da tela do KCM", revision="2026-09",
    section="foto da tela de alarme",
    note="observação direta da máquina; vale para esta máquina, nesta configuração.")

_ENTRIES: list[AlarmDefinition] = [
    AlarmDefinition(
        key=AlarmKey(Application.WBF, "KCM", 56),
        name="BELTLOAD LOW",
        meaning="carga na correia abaixo do mínimo aceito pelo controlador",
        severity=Severity.ALARM,
        evidence=EvidenceLevel.FIELD_OBSERVED,
        doc_ref=_REF_FOTO_TELA,
        scope="observado na aplicação WBF desta máquina; outra aplicação ou outro "
              "arquivo de configuração pode usar o código 56 para outra coisa",
        source="documento de campo 4 — foto da tela do KCM",
        observed_on=GTEX_WBF,
        reverse_warning="carga baixa na correia nem sempre chega a emitir 56: "
                        "depende do limite parametrizado e do tempo de permanência",
    ),
    AlarmDefinition(
        key=AlarmKey(Application.ANY, "KCM", 13),
        name="MDU SPEED DEV",
        meaning="desvio entre a velocidade comandada e a velocidade realimentada",
        severity=Severity.ALARM,
        # Rebaixado de propósito: há seção, não há revisão, e a origem não é do
        # fabricante. Promover exigiria manual com revisão identificada.
        evidence=EvidenceLevel.TECHNICAL_OPINION,
        doc_ref=_REF_SUPLEMENTO_29,
        scope="código citado na documentação interna do projeto; a associação com "
              "uma causa física (encoder, cabo, interface) NÃO está contida no código",
        source="contexto mestre §9; suplemento técnico §29–32 (sem revisão identificada)",
        reverse_warning="a mesma falha física pode aparecer sem o 13 (por exemplo, se o "
                        "desvio não atingir o limite) e o 13 pode surgir por parâmetro errado "
                        "de PICK UP TEETH, sem defeito de hardware",
    ),
    AlarmDefinition(
        key=AlarmKey(Application.ANY, "KCM", 8),
        name="BAD SFT STATUS",
        meaning="o controlador considerou inválido o status reportado por um SFT",
        severity=Severity.ALARM,
        evidence=EvidenceLevel.TECHNICAL_OPINION,
        doc_ref=_REF_GUIA_ALARMES,
        scope="um entre os códigos que podem acompanhar uma condição de SFT; "
              "NÃO é o único, e depende de qual condição o controlador detectou",
        source="guia PT-BR de alarmes; suplemento técnico §44 (sem revisão identificada)",
        reverse_warning="uma falha de SFT pode emitir outros códigos conforme a condição "
                        "(perda de comunicação, status fora de faixa, endereço ausente). "
                        "Nenhuma regra deste sistema assume SFT ⇒ 08.",
    ),
    AlarmDefinition(
        key=AlarmKey(Application.ANY, "KCM", 46),
        name="Drive Command High",
        meaning="comando de acionamento sustentado no alto da faixa",
        severity=Severity.WARNING,
        evidence=EvidenceLevel.TECHNICAL_OPINION,
        doc_ref=_REF_CONTEXTO,
        scope="código citado na documentação interna do projeto; o limite e o tempo que "
              "disparam dependem da parametrização da máquina",
        source="contexto mestre §9; suplemento técnico §29–32 (sem revisão identificada)",
        reverse_warning="Drive Command alto é condição normal em partida e em troca de "
                        "receita; sozinho não caracteriza defeito",
    ),
]

CATALOG: dict[AlarmKey, AlarmDefinition] = {d.key: d for d in _ENTRIES}


def unknown_alarm(code: int, application: Application = Application.ANY,
                  controller_model: str = ANY_MODEL) -> AlarmDefinition:
    """Código fora do catálogo. Registrado como desconhecido, nunca adivinhado."""
    return AlarmDefinition(
        key=AlarmKey(application, controller_model, code),
        name=f"CÓDIGO {code}",
        meaning="código não catalogado para esta aplicação/controlador",
        severity=Severity.WARNING,
        evidence=EvidenceLevel.UNKNOWN,
        scope="sem entrada no catálogo; o significado precisa ser confirmado na tela "
              "da máquina ou na tabela de alarmes do arquivo de configuração",
        source="UNKNOWN",
        reverse_warning="nada pode ser concluído a partir do número isolado",
    )


def lookup(code: int, application: Application = Application.WBF,
           controller_model: str = "KCM") -> AlarmDefinition:
    """Resolve a chave composta, do mais específico para o mais geral.

    Ordem: (app, modelo) → (ANY, modelo) → (app, ANY) → (ANY, ANY) → desconhecido.
    A busca nunca cai no "código puro": mesmo o último nível carrega a chave
    completa usada na consulta, para que o registro diga em que contexto valeu.
    """
    for key in (AlarmKey(application, controller_model, code),
                AlarmKey(Application.ANY, controller_model, code),
                AlarmKey(application, ANY_MODEL, code),
                AlarmKey(Application.ANY, ANY_MODEL, code)):
        found = CATALOG.get(key)
        if found is not None:
            return found
    return unknown_alarm(code, application, controller_model)


def catalog_for(application: Optional[Application] = None) -> list[AlarmDefinition]:
    """Entradas do catálogo, opcionalmente filtradas pela aplicação."""
    if application is None:
        return list(CATALOG.values())
    return [d for d in CATALOG.values()
            if d.key.application in (application, Application.ANY)]


def promotion_backlog() -> list[dict]:
    """O que falta para promover cada entrada a documentação rastreável.

    Transforma "a documentação está fraca" numa lista de itens acionáveis.
    """
    out = []
    for d in CATALOG.values():
        if d.evidence in (EvidenceLevel.MANUFACTURER_DOC, EvidenceLevel.MACHINE_DOC):
            continue
        faltam = d.doc_ref.missing if d.doc_ref.document != "UNKNOWN" else \
            ["documento", "revisão", "seção ou página"]
        out.append({"key": str(d.key), "name": d.name,
                    "current_level": d.evidence.value,
                    "have": d.doc_ref.cite(),
                    "missing": faltam,
                    "note": d.doc_ref.note})
    return out
