"""Backoff exponencial com jitter para reconexão.

Base 1 s, fator 2, teto 60 s, jitter ±20 %. O gerador aleatório é injetável
(random.Random(seed)) para o teste ser determinístico. O teto vale depois do jitter:
nenhum atraso passa de max_s.
"""

from __future__ import annotations

import random


class Backoff:
    def __init__(
        self,
        *,
        base_s: float = 1.0,
        factor: float = 2.0,
        max_s: float = 60.0,
        jitter: float = 0.2,
        seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        if base_s <= 0:
            raise ValueError("base_s deve ser > 0")
        if factor < 1:
            raise ValueError("factor deve ser >= 1")
        if max_s < base_s:
            raise ValueError("max_s deve ser >= base_s")
        if not 0 <= jitter < 1:
            raise ValueError("jitter deve estar em [0, 1)")
        self._base = base_s
        self._factor = factor
        self._max = max_s
        self._jitter = jitter
        # Jitter de reconexão, não criptografia: PRNG comum e semeável é o desejado.
        self._rng = rng if rng is not None else random.Random(seed)  # noqa: S311
        self._attempt = 0

    @property
    def attempt(self) -> int:
        """Quantas tentativas já foram consumidas desde o último reset."""
        return self._attempt

    @property
    def max_s(self) -> float:
        return self._max

    def peek(self) -> float:
        """Atraso base da próxima tentativa, sem jitter."""
        return min(self._base * (self._factor**self._attempt), self._max)

    def next_delay(self) -> float:
        """Próximo atraso em segundos. Cresce até o teto; o jitter nunca ultrapassa o teto."""
        raw = self.peek()
        if raw < self._max:
            self._attempt += 1
        spread = raw * self._jitter
        delay = raw + self._rng.uniform(-spread, spread) if spread > 0 else raw
        return min(max(delay, 0.0), self._max)

    def reset(self) -> None:
        """Volta ao atraso base. Chamado quando a comunicação volta a funcionar."""
        self._attempt = 0
