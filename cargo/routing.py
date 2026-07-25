"""Transparent route selection over a named demo map, not autonomous navigation."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Mapping

from .risk_map import ZoneRiskMap


DEMO_GRAPH: dict[str, tuple[tuple[str, float], ...]] = {
    "A1": (("A2", 1.0), ("B1", 1.0)),
    "A2": (("A1", 1.0), ("B2", 1.0)),
    "B1": (("A1", 1.0), ("C1", 1.0)),
    "B2": (("A2", 1.0), ("C2", 1.0)),
    "C1": (("B1", 1.0), ("C2", 2.0)),
    "C2": (("B2", 1.0), ("C1", 2.0)),
}


@dataclass(frozen=True)
class Route:
    nodes: tuple[str, ...]
    cost: float
    reason: str


def choose_route(graph: Mapping[str, tuple[tuple[str, float], ...]], risks: ZoneRiskMap, start: str, destination: str, cargo_type: str, blocked: set[str] | None = None) -> Route | None:
    if cargo_type not in {"standard", "fragile"}:
        raise ValueError("cargo_type must be standard or fragile")
    blocked = blocked or set()
    if start in blocked or destination in blocked or start not in graph or destination not in graph:
        return None
    distance_weight, risk_weight = ((1.0, 0.25) if cargo_type == "standard" else (0.25, 1.0))
    queue = [(0.0, start, (start,))]
    costs = {start: 0.0}
    while queue:
        cost, node, path = heapq.heappop(queue)
        if node == destination:
            policy = "shortest-first" if cargo_type == "standard" else "stability-first"
            return Route(path, round(cost, 3), f"{policy}; demo distance and learned zone-risk costs")
        if cost != costs.get(node):
            continue
        for neighbor, distance in graph[node]:
            if neighbor in blocked:
                continue
            next_cost = cost + distance_weight * distance + risk_weight * risks.score(neighbor)
            if next_cost < costs.get(neighbor, float("inf")):
                costs[neighbor] = next_cost
                heapq.heappush(queue, (next_cost, neighbor, path + (neighbor,)))
    return None
