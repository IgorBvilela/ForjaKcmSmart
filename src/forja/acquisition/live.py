"""Estado ao vivo por equipamento e detecção de STALE.

STALE é estado derivado: o último valor bom ficou velho segundo o relógio monotônico.
Ao expor, a qualidade vira STALE sem alterar valor nem ts_utc originais (a idade fica visível).
Nada daqui é gravado no historian.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from forja.domain import Clock, ConnectionState, Quality, Sample, SampleBatch

_NS = 1_000_000_000


class LiveSnapshot(BaseModel):
    """Foto do estado ao vivo: {tag: Sample} já com STALE aplicado, conexão e idade."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    equipment_id: str
    ts_utc: datetime
    connection: ConnectionState
    samples: dict[str, Sample]
    ages_s: dict[str, float | None]
    is_stale: bool
    stale_for_s: float | None
    last_ok_utc: datetime | None


class StaleMonitor:
    """Decide se um valor está velho a partir do relógio monotônico."""

    def __init__(self, clock: Clock, stale_after_s: float) -> None:
        if stale_after_s <= 0:
            raise ValueError("stale_after_s deve ser > 0")
        self._clock = clock
        self.stale_after_s = stale_after_s

    def age_s(self, mono_ns: int) -> float:
        return max(0.0, (self._clock.monotonic_ns() - mono_ns) / _NS)

    def is_stale(self, last_ok_mono_ns: int | None) -> bool:
        if last_ok_mono_ns is None:
            return False
        return self.age_s(last_ok_mono_ns) > self.stale_after_s

    def stale_for_s(self, last_ok_mono_ns: int | None) -> float | None:
        if last_ok_mono_ns is None or not self.is_stale(last_ok_mono_ns):
            return None
        return self.age_s(last_ok_mono_ns) - self.stale_after_s

    @staticmethod
    def as_stale(sample: Sample, age_s: float) -> Sample:
        """Cópia com quality=STALE. Valor e ts_utc ficam exatamente como vieram."""
        return sample.model_copy(
            update={
                "quality": Quality.STALE,
                "reason_pt": f"Valor antigo: sem leitura nova há {age_s:.0f} s",
            }
        )


class LiveState:
    """Último Sample por tag de um equipamento, com STALE aplicado na exposição.

    Regra de exposição por tag:
    - última leitura usável (GOOD/SIMULATED/UNCERTAIN) fresca: sai como veio;
    - última leitura usável velha: sai com quality STALE, valor e ts intactos;
    - última leitura BAD: sai BAD (é uma leitura, só que inválida);
    - COMM_ERROR agora, mas houve valor antes: sai o valor anterior (fresco ou STALE);
    - COMM_ERROR sem valor anterior: sai COMM_ERROR.
    Samples STALE recebidos são ignorados: STALE nunca é entrada, só saída.
    """

    def __init__(self, equipment_id: str, clock: Clock, stale_after_s: float) -> None:
        self.equipment_id = equipment_id
        self._clock = clock
        self.monitor = StaleMonitor(clock, stale_after_s)
        self._last: dict[str, Sample] = {}
        self._last_mono: dict[str, int] = {}
        self._last_ok: dict[str, Sample] = {}
        self._last_ok_mono: dict[str, int] = {}
        self._newest_ok_mono: int | None = None
        self._newest_ok_utc: datetime | None = None

    def update(self, batch: SampleBatch) -> None:
        now = self._clock.monotonic_ns()
        for s in batch.samples:
            if s.quality is Quality.STALE:
                continue
            self._last[s.tag] = s
            self._last_mono[s.tag] = now
            if s.quality.is_usable_value and s.value is not None:
                self._last_ok[s.tag] = s
                self._last_ok_mono[s.tag] = now
                self._newest_ok_mono = now
                self._newest_ok_utc = s.ts_utc

    def clear(self) -> None:
        self._last.clear()
        self._last_mono.clear()
        self._last_ok.clear()
        self._last_ok_mono.clear()
        self._newest_ok_mono = None
        self._newest_ok_utc = None

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(self._last)

    @property
    def last_ok_utc(self) -> datetime | None:
        return self._newest_ok_utc

    @property
    def is_stale(self) -> bool:
        """Houve valor bom e o mais recente deles já passou de stale_after_s."""
        return self.monitor.is_stale(self._newest_ok_mono)

    @property
    def stale_for_s(self) -> float | None:
        return self.monitor.stale_for_s(self._newest_ok_mono)

    def sample(self, tag: str) -> tuple[Sample, float] | None:
        """Sample exposto e idade em segundos, ou None se a tag nunca apareceu."""
        latest = self._last.get(tag)
        if latest is None:
            return None
        if latest.quality is Quality.BAD:
            return latest, self.monitor.age_s(self._last_mono[tag])
        ok = self._last_ok.get(tag)
        if ok is None:
            return latest, self.monitor.age_s(self._last_mono[tag])
        ok_mono = self._last_ok_mono[tag]
        age = self.monitor.age_s(ok_mono)
        if self.monitor.is_stale(ok_mono):
            return self.monitor.as_stale(ok, age), age
        return ok, age

    def snapshot(self, connection: ConnectionState) -> LiveSnapshot:
        samples: dict[str, Sample] = {}
        ages: dict[str, float | None] = {}
        for tag in self._last:
            exposed = self.sample(tag)
            if exposed is None:
                continue
            samples[tag], ages[tag] = exposed
        return LiveSnapshot(
            equipment_id=self.equipment_id,
            ts_utc=self._clock.now_utc(),
            connection=connection,
            samples=samples,
            ages_s=ages,
            is_stale=self.is_stale,
            stale_for_s=self.stale_for_s,
            last_ok_utc=self._newest_ok_utc,
        )
