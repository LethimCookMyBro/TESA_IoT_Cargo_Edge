"""Small, explicit demo zone-risk memory; this is not localization or SLAM."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from math import isfinite
from time import time


@dataclass(frozen=True)
class ZoneRisk:
    score: float
    observations: int
    surface: str | None
    updated_ms: int


class ZoneRiskMap:
    def __init__(self, history_size: int = 20) -> None:
        self._history_size = history_size
        self._scores: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=history_size))
        self._surfaces: dict[str, str] = {}
        self._updated_ms: dict[str, int] = {}

    def observe(self, zone: str, normalized_score: float, surface: str | None = None) -> ZoneRisk:
        if not zone or not isfinite(normalized_score) or not 0 <= normalized_score <= 1:
            raise ValueError("zone and a normalized score from 0 to 1 are required")
        values = self._scores[zone]
        values.append(float(normalized_score))
        if surface:
            self._surfaces[zone] = surface
        self._updated_ms[zone] = int(time() * 1000)
        return self.get(zone)

    def get(self, zone: str) -> ZoneRisk:
        values = self._scores.get(zone)
        if not values:
            return ZoneRisk(0.0, 0, None, 0)
        return ZoneRisk(sum(values) / len(values), len(values), self._surfaces.get(zone), self._updated_ms[zone])

    def score(self, zone: str) -> float:
        return self.get(zone).score

    def as_dict(self) -> dict[str, dict]:
        return {zone: self.get(zone).__dict__ for zone in sorted(self._scores)}
