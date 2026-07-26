"""Deterministic multi-robot simulator built on the production contracts.

What is real and what is not, stated once and enforced everywhere below:

* ``prediction`` comes from the **real** trained model (``SurfaceClassifier``) run over **real
  stored CareerCon windows**. Labels, confidences and vibration scores are genuine model output.
* ``channels`` are **synthesised** values in the installed Bitstream catalog's units. They are not
  a unit conversion of the dataset and they are not sensor measurements. Every sample carries
  ``provenance: SIMULATED`` for exactly this reason.
* Nothing here claims localization, a real obstacle sensor, or physical movement. ``zone`` is a
  node of the planned route, not a measured position.

Given the same seed the same samples come out, so an evidence run is reproducible.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, Iterator

from . import contracts
from .fleet import sample
from .inference import SurfaceClassifier
from .sources import DatasetReplaySource

HEALTHY, HIGH_VIBRATION, FAULTY = "healthy", "high_vibration", "faulty"

# Train-disjoint validation windows chosen so each profile exercises a different part of the
# model's response. They drive a demo, never the held-out test metrics.
PROFILE_WINDOWS = {
    HEALTHY: (2460, 526, 2462, 5144, 2175),
    HIGH_VIBRATION: (1244, 2235, 5733, 2220, 1238),
    FAULTY: (2460, 2462, 5144, 2220, 1238),
}

GRAVITY_MS2 = 9.81

# Decimal places kept from model output so a seeded run is byte-reproducible. See predict().
REPRODUCIBLE_DIGITS = 9


@dataclass(frozen=True)
class ScenarioRobot:
    robot_id: str
    profile: str
    cargo_type: str
    pickup: str
    destination: str
    description: str


FLEET = (
    ScenarioRobot("robot-alpha", HEALTHY, "standard", "A1", "C2",
                  "healthy robot on a low-risk route"),
    ScenarioRobot("robot-bravo", HIGH_VIBRATION, "fragile", "A1", "C2",
                  "accumulates vibration and impact exposure, then re-plans a safer next route"),
    ScenarioRobot("robot-charlie", FAULTY, "standard", "A1", "C2",
                  "stale, malformed, out-of-order and contradictory sensor data"),
)


class ScenarioSource:
    """Loads the real model and real stored windows once, then serves every robot."""

    def __init__(self, root: Path) -> None:
        self.root = root
        labels = {int(key): value for key, value in
                  json.loads((root / "models" / "label_mapping.json").read_text(encoding="utf-8")).items()}
        self.dataset = DatasetReplaySource(root / "dataset", labels)
        self.model = SurfaceClassifier(root / "models")

    def predict(self, index: int) -> dict[str, Any]:
        window, ground_truth = self.dataset.window(index)
        result = self.model.predict(window)
        quantiles = self.model.config["risk_quantiles"]
        return {
            "label": result["label"],
            # Rounded to REPRODUCIBLE_DIGITS: the ensemble's predict_proba sums tree votes in a
            # thread-dependent order, so two identical calls can differ by one unit in the last
            # place. That drift is far below any meaningful confidence difference, but it would
            # make a seeded scenario irreproducible, so it is rounded away here.
            "confidence": round(result["confidence"], REPRODUCIBLE_DIGITS),
            "vibration_risk": result["vibration_risk"],
            # Normalised to 0..1 for the zone risk map, using the same quantile the engine uses.
            "vibration_score": round(min(1.0, result["vibration_score"] / max(1e-9, quantiles["medium_to_high"])), REPRODUCIBLE_DIGITS),
            "features": {"accel_spread": round(result["vibration_score"], REPRODUCIBLE_DIGITS)},
            "window_index": index,
            "ground_truth": ground_truth,
            "model_input_provenance": "DATASET",
        }


def _channels(rng: Random, *, agitation: float) -> dict[str, float]:
    """Synthesised catalog-unit channels. `agitation` scales the motion, nothing else."""
    return {
        "bmi270.accelX": round(rng.gauss(0.0, agitation), 4),
        "bmi270.accelY": round(rng.gauss(0.0, agitation), 4),
        "bmi270.accelZ": round(GRAVITY_MS2 + rng.gauss(0.0, agitation), 4),
        "bmi270.gyroX": round(rng.gauss(0.0, agitation * 0.1), 4),
        "bmi270.gyroY": round(rng.gauss(0.0, agitation * 0.1), 4),
        "bmi270.gyroZ": round(rng.gauss(0.0, agitation * 0.1), 4),
        "bmi270.temperatureC": round(rng.uniform(26.0, 28.0), 2),
        "sht40.temperatureC": round(rng.uniform(24.0, 26.0), 2),
        "sht40.humidityPct": round(rng.uniform(40.0, 55.0), 2),
        "dps368.pressureHpa": round(rng.uniform(1008.0, 1014.0), 2),
    }


def samples(robot: ScenarioRobot, source: ScenarioSource, *, seed: int, count: int,
            zones: tuple[str, ...], start_ms: int = 0, interval_ms: int = 100) -> Iterator[dict[str, Any]]:
    """Yield `count` production-shaped telemetry payloads for one robot. Deterministic in `seed`."""
    rng = Random(f"{seed}:{robot.robot_id}")
    windows = PROFILE_WINDOWS[robot.profile]
    for step in range(count):
        observed_ms = start_ms + step * interval_ms
        seq = step + 1
        zone = zones[min(step * len(zones) // count, len(zones) - 1)] if zones else None
        prediction = source.predict(windows[step % len(windows)])

        if robot.profile == HEALTHY:
            channels = _channels(rng, agitation=0.05)

        elif robot.profile == HIGH_VIBRATION:
            channels = _channels(rng, agitation=0.9)
            # One impact, mid-run: an abrupt step far larger than the catalog's plausible change.
            # This is what makes the deterministic policy latch a Safe Stop on the spot.
            if step == count // 2:
                channels["bmi270.accelX"] = 19.5

        else:  # FAULTY -- one distinct fault per step, cycling
            channels = _channels(rng, agitation=0.05)
            fault = step % 5
            if fault == 1:
                channels["bmi270.accelY"] = float("nan")          # non-finite
            elif fault == 2:
                channels["dps368.pressureHpa"] = 5000.0           # outside the catalog range
            elif fault == 3:
                # Two sensors that both publish temperatureC, disagreeing by far more than drift.
                channels["sht40.temperatureC"] = 5.0
                channels["bmi270.temperatureC"] = 70.0
            elif fault == 4:
                observed_ms = start_ms                            # timestamp regression / stale
                seq = 1                                           # and a sequence regression

        payload = sample(robot.robot_id, seq=seq, observed_ms=observed_ms, channels=channels,
                         provenance="SIMULATED", source_mode=f"simulator:{robot.profile}",
                         zone=zone, prediction=prediction)
        yield payload
        # A duplicate delivery, so the sequence gate is exercised by the scenario and not only by
        # a unit test. The gate must refuse it without disturbing the robot's rolling state.
        if robot.profile == FAULTY and step % 5 == 0:
            yield json.loads(json.dumps(payload))


def demo() -> None:
    """Self-check: run with `python -m cargo.simulator`."""
    root = Path(__file__).resolve().parents[1]
    source = ScenarioSource(root)
    zones = ("A1", "A2", "B2", "C2")

    # `event_id` and `received_ms` are per-delivery by design, so reproducibility is asserted over
    # the content a rerun must reproduce, not over the envelope's identity fields.
    # Serialised rather than compared directly: the faulty profile deliberately injects NaN, and
    # NaN != NaN would make an otherwise identical rerun look non-reproducible.
    def content(payload: dict[str, Any]) -> str:
        return json.dumps({key: payload[key] for key in ("robot_id", "seq", "observed_ms", "provenance",
                                                         "source_mode", "zone", "channels", "prediction")},
                          sort_keys=True)

    for robot in FLEET:
        first = list(samples(robot, source, seed=7, count=6, zones=zones))
        second = list(samples(robot, source, seed=7, count=6, zones=zones))
        assert [content(p) for p in first] == [content(p) for p in second], \
            f"{robot.robot_id} is not reproducible for a fixed seed"
        for payload in first:
            contracts.validate_envelope(payload)
            assert payload["provenance"] == "SIMULATED"
            assert payload["zone"] in zones
            assert 0.0 <= payload["prediction"]["confidence"] <= 1.0

    faulty = list(samples(FLEET[2], source, seed=7, count=6, zones=zones))
    assert len(faulty) > 6, "the faulty profile must emit duplicate deliveries"
    different = list(samples(FLEET[0], source, seed=8, count=6, zones=zones))
    assert different[0]["channels"] != list(samples(FLEET[0], source, seed=7, count=6, zones=zones))[0]["channels"]
    print("cargo.simulator self-check passed")


if __name__ == "__main__":
    demo()
