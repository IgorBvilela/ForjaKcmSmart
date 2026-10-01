"""Scheduler de aquisição.

Ciclo: decide quais tags estão vencidas → driver.read() → normalize() →
lote para o historian → atualiza "últimos valores" para a API.

PERDA DE COMUNICAÇÃO — dois fatos, nunca confundidos:

    1. A TENTATIVA falhou agora          -> ReadError (quality COMM_ERROR)
       Registrado em `read_error`, com o instante exato e o erro do driver.

    2. O VALOR EXIBIDO é antigo          -> Sample (quality STALE)
       O último valor bom é reemitido, marcado como STALE e carregando
       `source_ts` = instante da leitura boa que o originou. A idade do
       número fica calculável (Sample.age_s), em vez de implícita.

Os dois são gerados no mesmo ciclo. Um ciclo de falha produz N ReadError
*e* N Sample STALE. Quem nunca teve leitura boa não tem valor a manter:
nesse caso sai Sample com quality COMM_ERROR e valor vazio.

Quem transforma isso em evento COMMUNICATION_LOSS é o motor de eventos,
não o scheduler.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from forja.domain.equipment import EquipmentCard
from forja.domain.models import Quality, ReadError, Sample, TAG_CATALOG, utcnow
from forja.drivers.base import KcmDriver
from forja.historian.repository import HistorianRepository

from .normalizer import normalize

log = logging.getLogger("forja.acquisition")


@dataclass
class TagState:
    period_s: float
    next_due: float = 0.0
    last_good: Optional[Sample] = None
    last_ts: Optional[datetime] = None
    consecutive_failures: int = 0


@dataclass
class CycleResult:
    """O que um ciclo de aquisição produziu.

    `samples` é o que a UI mostra (pode conter STALE).
    `read_errors` é o que aconteceu na tentativa de ler (COMM_ERROR).
    Manter os dois separados é o ponto: "falhou agora" != "este valor é velho".
    """
    samples: list[Sample] = field(default_factory=list)
    read_errors: list[ReadError] = field(default_factory=list)
    ts: datetime = field(default_factory=utcnow)
    communication_degraded: bool = False   # falhas consecutivas >= stale_after_cycles

    @property
    def ok(self) -> bool:
        return not self.read_errors


@dataclass
class AcquisitionStats:
    cycles: int = 0
    samples_written: int = 0
    read_failures: int = 0
    read_errors_written: int = 0
    consecutive_failed_cycles: int = 0
    last_cycle_ts: Optional[datetime] = None
    last_good_cycle_ts: Optional[datetime] = None
    connected: bool = False


class AcquisitionScheduler:
    def __init__(self, driver: KcmDriver, equipment: EquipmentCard, historian: HistorianRepository,
                 base_cycle_s: float = 1.0, stale_after_cycles: int = 3,
                 on_cycle: Optional[Callable[[CycleResult], None]] = None):
        self.driver = driver
        self.equipment = equipment
        self.historian = historian
        self.base_cycle_s = base_cycle_s
        # a partir de quantos ciclos consecutivos de falha a comunicação é
        # considerada degradada (o motor de eventos usa isso para abrir COMMUNICATION_LOSS)
        self.stale_after_cycles = stale_after_cycles
        self.on_cycle = on_cycle              # gancho do motor de eventos
        self.stats = AcquisitionStats()
        self._tags: dict[str, TagState] = {}
        self._latest: dict[str, Sample] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        for m in equipment.mappings:
            self._tags[m.tag] = TagState(period_s=m.poll_period_s)
        if not self._tags:   # sem mapeamento explícito: historiza o catálogo inteiro
            for name in TAG_CATALOG:
                self._tags[name] = TagState(period_s=base_cycle_s)

    # -- ciclo de vida
    def start(self) -> None:
        self.driver.connect()
        self._thread = threading.Thread(target=self._loop, name="forja-acquisition", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.driver.disconnect()

    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self.cycle()
            except Exception:              # o coletor nunca morre por uma exceção de ciclo
                log.exception("erro no ciclo de aquisição")
            elapsed = time.monotonic() - t0
            self._stop.wait(max(0.05, self.base_cycle_s - elapsed))

    # -- um ciclo (também usado nos testes, sem thread)
    def cycle(self) -> CycleResult:
        now = time.monotonic()
        due = [t for t, st in self._tags.items() if st.next_due <= now]
        if not due:
            return CycleResult()

        reads = self.driver.read(due)
        result = CycleResult()
        for raw in reads:
            st = self._tags[raw.tag]
            st.next_due = now + st.period_s
            s = normalize(raw, self.equipment, self.driver.source)
            if s is not None:
                st.last_good = s
                st.last_ts = s.ts
                st.consecutive_failures = 0
                result.samples.append(s)
            else:
                # FATO 1: a tentativa de leitura falhou agora
                st.consecutive_failures += 1
                self.stats.read_failures += 1
                result.read_errors.append(ReadError(
                    ts=utcnow(), equipment_id=self.equipment.equipment_id, tag=raw.tag,
                    source=self.driver.source, error=raw.error or "leitura falhou",
                    consecutive=st.consecutive_failures))
                # FATO 2: o valor que continuamos exibindo é antigo
                result.samples.append(self._held_value(raw.tag, st))

        if result.read_errors:
            self.stats.consecutive_failed_cycles += 1
        else:
            self.stats.consecutive_failed_cycles = 0
            self.stats.last_good_cycle_ts = result.ts
        result.communication_degraded = self.stats.consecutive_failed_cycles >= self.stale_after_cycles

        health = self.driver.health()
        self.stats.connected = health.connected

        if result.samples:
            self.historian.write_samples(result.samples)
            self.stats.samples_written += len(result.samples)
            with self._lock:
                for s in result.samples:
                    self._latest[s.tag] = s
        if result.read_errors:
            self.historian.write_read_errors(result.read_errors)
            self.stats.read_errors_written += len(result.read_errors)

        self.stats.cycles += 1
        self.stats.last_cycle_ts = utcnow()
        if self.on_cycle:
            self.on_cycle(result)
        return result

    def _held_value(self, tag: str, st: TagState) -> Sample:
        """O valor que o sistema continua mostrando quando a leitura falhou.

        Com último valor bom: reemite marcado como STALE, carregando o
        timestamp de origem para que a idade do número seja explícita.
        Sem nenhum valor bom ainda: não há o que manter — COMM_ERROR e vazio.
        """
        if st.last_good is not None:
            return Sample(ts=utcnow(), equipment_id=self.equipment.equipment_id, tag=tag,
                          value=st.last_good.value, quality=Quality.STALE,
                          source=self.driver.source, source_ts=st.last_good.ts)
        return Sample(ts=utcnow(), equipment_id=self.equipment.equipment_id, tag=tag,
                      value="", quality=Quality.COMM_ERROR, source=self.driver.source)

    # -- consulta
    def latest(self) -> dict[str, Sample]:
        with self._lock:
            return dict(self._latest)
