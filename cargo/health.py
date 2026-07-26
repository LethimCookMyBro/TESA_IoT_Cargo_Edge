"""Deterministic sensor and robot health. No model, no LLM, no network call on this path.

Every check here runs in memory against a bounded rolling window and answers with an explicit
state and a human-readable reason. A channel that is not present in a sample is not checked and
not guessed at — the report says which channels were actually evaluated.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from math import isfinite, sqrt
from typing import Any, Mapping

HEALTHY, DEGRADED, UNSAFE, OFFLINE = "HEALTHY", "DEGRADED", "UNSAFE", "OFFLINE"

# Ordered worst-last so a report can take the maximum of several findings.
SEVERITY = {HEALTHY: 0, DEGRADED: 1, OFFLINE: 2, UNSAFE: 3}


@dataclass(frozen=True)
class ChannelLimit:
    """A plausibility band for one channel, with the evidence it rests on.

    ``source`` is deliberately part of the data: a limit whose provenance cannot be stated is a
    fabricated hardware claim. ``DATASHEET`` limits are the sensor's published operating range and
    are safe to enforce; they are *not* a claim that the installed Bitstream build exposes the
    channel. A channel absent from a sample is simply never checked.
    """

    unit: str
    minimum: float
    maximum: float
    source: str
    # Largest believable change between consecutive samples. None disables the rate check.
    max_step: float | None = None
    # A channel that does not move by at least this much across a full window is stuck.
    flatline_epsilon: float | None = None


# Ranges, units and field names below are the *installed* Bitstream Studio 0.1.9 telemetry catalog
# (catalog version "2026-07-13"), not generic datasheet values -- the two disagree, and the catalog
# wins because it is what a real board would actually publish. Notably accel is m/s^2 in -20..20
# (not g), gyro is rad/s in -5..5 (not deg/s), and BMM350 is +/-1000 uT (not +/-2000).
# Keys are namespaced `{sensor}.{catalogField}` because four sensors each publish `temperatureC`.
CATALOG_SOURCE = "Bitstream Studio 0.1.9 sensor catalog 2026-07-13"

CHANNEL_LIMITS: dict[str, ChannelLimit] = {
    "bmi270.accelX": ChannelLimit("m/s^2", -20.0, 20.0, CATALOG_SOURCE, max_step=15.0, flatline_epsilon=1e-4),
    "bmi270.accelY": ChannelLimit("m/s^2", -20.0, 20.0, CATALOG_SOURCE, max_step=15.0, flatline_epsilon=1e-4),
    "bmi270.accelZ": ChannelLimit("m/s^2", -20.0, 20.0, CATALOG_SOURCE, max_step=15.0, flatline_epsilon=1e-4),
    "bmi270.gyroX": ChannelLimit("rad/s", -5.0, 5.0, CATALOG_SOURCE, max_step=4.0, flatline_epsilon=1e-4),
    "bmi270.gyroY": ChannelLimit("rad/s", -5.0, 5.0, CATALOG_SOURCE, max_step=4.0, flatline_epsilon=1e-4),
    "bmi270.gyroZ": ChannelLimit("rad/s", -5.0, 5.0, CATALOG_SOURCE, max_step=4.0, flatline_epsilon=1e-4),
    "bmi270.temperatureC": ChannelLimit("degC", -40.0, 85.0, CATALOG_SOURCE, max_step=5.0),
    "bmi270.headingRad": ChannelLimit("rad", -3.15, 3.15, CATALOG_SOURCE),
    "bmi270.pitchRad": ChannelLimit("rad", -1.6, 1.6, CATALOG_SOURCE),
    "bmi270.rollRad": ChannelLimit("rad", -3.15, 3.15, CATALOG_SOURCE),
    "bmm350.magX": ChannelLimit("uT", -1000.0, 1000.0, CATALOG_SOURCE, max_step=400.0),
    "bmm350.magY": ChannelLimit("uT", -1000.0, 1000.0, CATALOG_SOURCE, max_step=400.0),
    "bmm350.magZ": ChannelLimit("uT", -1000.0, 1000.0, CATALOG_SOURCE, max_step=400.0),
    "bmm350.temperatureC": ChannelLimit("degC", -40.0, 85.0, CATALOG_SOURCE, max_step=5.0),
    "sht40.temperatureC": ChannelLimit("degC", -40.0, 125.0, CATALOG_SOURCE, max_step=5.0),
    "sht40.humidityPct": ChannelLimit("%RH", 0.0, 100.0, CATALOG_SOURCE, max_step=25.0),
    "dps368.pressureHpa": ChannelLimit("hPa", 300.0, 1200.0, CATALOG_SOURCE, max_step=20.0),
    "dps368.temperatureC": ChannelLimit("degC", -40.0, 85.0, CATALOG_SOURCE, max_step=5.0),
    "adc.pot1Mv": ChannelLimit("mV", 0.0, 1800.0, CATALOG_SOURCE, max_step=1800.0),
    "adc.pot2Mv": ChannelLimit("mV", 0.0, 1800.0, CATALOG_SOURCE, max_step=1800.0),
    "adc.pot3Mv": ChannelLimit("mV", 0.0, 1800.0, CATALOG_SOURCE, max_step=1800.0),
    "adc.pot4Mv": ChannelLimit("mV", 0.0, 1800.0, CATALOG_SOURCE, max_step=1800.0),
}

# Catalog default publish intervals, so staleness is judged per sensor instead of by one guess.
DEFAULT_PUBLISH_INTERVAL_MS = {
    "bmi270": 50, "bmm350": 200, "sht40": 500, "dps368": 1000, "adc": 200, "sw_btn": 20,
}

# Four sensors publish a `temperatureC`. If they disagree badly, at least one of them is lying.
TEMPERATURE_CHANNELS = ("bmi270.temperatureC", "bmm350.temperatureC", "sht40.temperatureC", "dps368.temperatureC")
TEMPERATURE_DISAGREEMENT_C = 15.0

# Earth's field is roughly 25-65 uT and the catalog's own gauge hint is +/-100 uT. A norm outside
# this band is a magnet, a fault, or a bad unit conversion; the heading must not be trusted.
MAGNETIC_NORM_MIN_UT, MAGNETIC_NORM_MAX_UT = 10.0, 100.0
QUATERNION_NORM_TOLERANCE = 0.05
QUATERNION_CHANNELS = ("bmi270.quatW", "bmi270.quatX", "bmi270.quatY", "bmi270.quatZ")
MAGNETIC_VECTOR_CHANNELS = ("bmm350.magX", "bmm350.magY", "bmm350.magZ")

# A channel that trips this many consecutive times is quarantined rather than re-reported forever.
QUARANTINE_AFTER = 3


@dataclass
class HealthReport:
    state: str
    reasons: list[str] = field(default_factory=list)
    channels_checked: tuple[str, ...] = ()
    quarantined: tuple[str, ...] = ()
    # Counters an operator can see, so a transport problem is visible rather than inferred.
    dropped: int = 0
    duplicates: int = 0
    out_of_order: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state, "reasons": list(self.reasons),
            "channels_checked": list(self.channels_checked), "quarantined": list(self.quarantined),
            "dropped": self.dropped, "duplicates": self.duplicates, "out_of_order": self.out_of_order,
        }


class HealthMonitor:
    """Rolling health for exactly one robot. Never shared between robots.

    ``expected_interval_ms`` comes from the configured sample rate; staleness is judged against it
    rather than a fixed constant, so a slow simulated robot is not reported as failing.
    """

    def __init__(self, robot_id: str, *, expected_interval_ms: int = 1000, window: int = 16,
                 stale_multiplier: float = 3.0) -> None:
        self.robot_id = robot_id
        self.expected_interval_ms = expected_interval_ms
        self.stale_multiplier = stale_multiplier
        self._window = window
        self._values: dict[str, deque[float]] = {}
        self._strikes: dict[str, int] = {}
        self.quarantined: set[str] = set()
        self.last_observed_ms: int | None = None
        self.dropped = self.duplicates = self.out_of_order = 0
        self.connected = True

    # ---------- transport-level counters, fed by the ingest boundary ----------

    def note_duplicate(self) -> None:
        self.duplicates += 1

    def note_out_of_order(self) -> None:
        self.out_of_order += 1

    def note_dropped(self, count: int = 1) -> None:
        self.dropped += count

    def note_disconnect(self) -> None:
        """Transport loss. Rolling windows are cleared: values from before a gap are not neighbours."""
        self.connected = False
        self._values.clear()

    def note_reconnect(self) -> None:
        self.connected = True
        self.last_observed_ms = None

    # ---------- bounded software recovery ----------

    def release_channel(self, channel: str) -> None:
        """Un-quarantine a channel once an operator has acknowledged it."""
        self.quarantined.discard(channel)
        self._strikes.pop(channel, None)
        self._values.pop(channel, None)

    def _strike(self, channel: str) -> None:
        self._strikes[channel] = self._strikes.get(channel, 0) + 1
        if self._strikes[channel] >= QUARANTINE_AFTER:
            self.quarantined.add(channel)
            # Drop only this channel's window. Every other channel keeps its valid history.
            self._values.pop(channel, None)

    def _clear_strike(self, channel: str) -> None:
        self._strikes.pop(channel, None)

    # ---------- the deterministic evaluation ----------

    def observe(self, channels: Mapping[str, Any], *, observed_ms: int, now_ms: int) -> HealthReport:
        """Score one sample. Pure function of this monitor's state plus the sample."""
        reasons: list[str] = []
        worst = HEALTHY
        checked: list[str] = []

        def raise_to(state: str, reason: str) -> None:
            nonlocal worst
            reasons.append(reason)
            if SEVERITY[state] > SEVERITY[worst]:
                worst = state

        if not self.connected:
            raise_to(OFFLINE, "transport is disconnected")

        # Timestamp regression: a sample older than the last accepted one cannot extend a window.
        if self.last_observed_ms is not None and observed_ms < self.last_observed_ms:
            raise_to(DEGRADED, f"timestamp regression: {observed_ms} < {self.last_observed_ms}")
        else:
            self.last_observed_ms = observed_ms

        stale_after = self.expected_interval_ms * self.stale_multiplier
        age_ms = now_ms - observed_ms
        if age_ms > stale_after:
            raise_to(UNSAFE if age_ms > stale_after * 2 else DEGRADED,
                     f"sample is {age_ms} ms old; expected one every {self.expected_interval_ms} ms")

        for channel, raw in channels.items():
            limit = CHANNEL_LIMITS.get(channel)
            if limit is None or channel in self.quarantined:
                continue
            checked.append(channel)
            if isinstance(raw, bool):
                self._strike(channel)
                raise_to(UNSAFE, f"{channel} is not a number: {raw!r}")
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                self._strike(channel)
                raise_to(UNSAFE, f"{channel} is not a number: {raw!r}")
                continue
            if not isfinite(value):
                self._strike(channel)
                raise_to(UNSAFE, f"{channel} is not finite: {value!r}")
                continue
            if not limit.minimum <= value <= limit.maximum:
                self._strike(channel)
                raise_to(UNSAFE, f"{channel}={value:g} {limit.unit} is outside {limit.minimum:g}..{limit.maximum:g} ({limit.source})")
                continue

            window = self._values.setdefault(channel, deque(maxlen=self._window))
            if window and limit.max_step is not None and abs(value - window[-1]) > limit.max_step:
                self._strike(channel)
                raise_to(UNSAFE, f"{channel} jumped {abs(value - window[-1]):g} {limit.unit} in one sample (impact or fault)")
            elif (limit.flatline_epsilon is not None and len(window) == window.maxlen
                  and max(window) - min(window) < limit.flatline_epsilon):
                self._strike(channel)
                raise_to(DEGRADED, f"{channel} has not moved across {window.maxlen} samples (stuck channel)")
            else:
                self._clear_strike(channel)
            window.append(value)

        self._check_temperatures(channels, raise_to)
        self._check_magnetic(channels, raise_to)
        self._check_quaternion(channels, raise_to)

        if self.quarantined:
            raise_to(DEGRADED, f"quarantined channels: {', '.join(sorted(self.quarantined))}")

        return HealthReport(worst, reasons, tuple(checked), tuple(sorted(self.quarantined)),
                            self.dropped, self.duplicates, self.out_of_order)

    def _check_temperatures(self, channels: Mapping[str, Any], raise_to) -> None:
        readings = {}
        for name in TEMPERATURE_CHANNELS:
            if name not in channels or name in self.quarantined or isinstance(channels[name], bool):
                continue
            try:
                value = float(channels[name])
            except (TypeError, ValueError):
                continue
            if isfinite(value):
                readings[name] = value
        if len(readings) < 2:
            return
        spread = max(readings.values()) - min(readings.values())
        if spread > TEMPERATURE_DISAGREEMENT_C:
            raise_to(DEGRADED, f"temperature channels disagree by {spread:.1f} degC: "
                               + ", ".join(f"{name}={value:.1f}" for name, value in sorted(readings.items())))

    def _check_magnetic(self, channels: Mapping[str, Any], raise_to) -> None:
        parts = [channels.get(axis) for axis in MAGNETIC_VECTOR_CHANNELS]
        if any(part is None for part in parts) or self.quarantined & set(MAGNETIC_VECTOR_CHANNELS):
            return
        try:
            values = [float(part) for part in parts]
        except (TypeError, ValueError):
            raise_to(DEGRADED, "magnetic vector is not numeric")
            return
        if not all(isfinite(value) for value in values):
            raise_to(DEGRADED, "magnetic vector is not finite")
            return
        norm = sqrt(sum(value * value for value in values))
        if not MAGNETIC_NORM_MIN_UT <= norm <= MAGNETIC_NORM_MAX_UT:
            raise_to(DEGRADED, f"magnetic field norm {norm:.1f} uT is implausible for Earth's field "
                               f"({MAGNETIC_NORM_MIN_UT:g}..{MAGNETIC_NORM_MAX_UT:g} uT); heading is not trustworthy")

    def _check_quaternion(self, channels: Mapping[str, Any], raise_to) -> None:
        parts = [channels.get(axis) for axis in QUATERNION_CHANNELS]
        if any(part is None for part in parts):
            return
        try:
            values = [float(part) for part in parts]
        except (TypeError, ValueError):
            raise_to(UNSAFE, "orientation quaternion is not numeric")
            return
        if not all(isfinite(value) for value in values):
            raise_to(UNSAFE, "orientation quaternion is not finite")
            return
        norm = sqrt(sum(value * value for value in values))
        if abs(norm - 1.0) > QUATERNION_NORM_TOLERANCE:
            raise_to(UNSAFE, f"orientation quaternion norm {norm:.3f} is not 1 (+/-{QUATERNION_NORM_TOLERANCE}); orientation is invalid")


def demo() -> None:
    """Self-check: run with `python -m cargo.health`."""
    good = {"bmi270.accelX": 0.1, "bmi270.accelY": 0.0, "bmi270.accelZ": 9.81,
            "sht40.humidityPct": 45.0, "sht40.temperatureC": 24.0, "bmi270.temperatureC": 26.0}

    monitor = HealthMonitor("robot-01", expected_interval_ms=100)
    assert monitor.observe(good, observed_ms=1000, now_ms=1000).state == HEALTHY

    # Non-finite and out-of-range are unsafe, not merely degraded. 25 m/s^2 is outside the
    # catalog's -20..20 band; the same number would have passed a generic +/-16 g datasheet check.
    assert HealthMonitor("r", expected_interval_ms=100).observe(
        {"bmi270.accelX": float("nan")}, observed_ms=1, now_ms=1).state == UNSAFE
    assert HealthMonitor("r", expected_interval_ms=100).observe(
        {"bmi270.accelX": 25.0}, observed_ms=1, now_ms=1).state == UNSAFE
    assert HealthMonitor("r", expected_interval_ms=100).observe(
        {"dps368.pressureHpa": 5.0}, observed_ms=1, now_ms=1).state == UNSAFE
    # Catalog units matter: 100 rad/s would be a plausible deg/s reading and must still be rejected.
    assert HealthMonitor("r", expected_interval_ms=100).observe(
        {"bmi270.gyroX": 100.0}, observed_ms=1, now_ms=1).state == UNSAFE

    # Stale beyond twice the tolerance is unsafe; mildly stale is degraded.
    mild = HealthMonitor("r", expected_interval_ms=100).observe(good, observed_ms=0, now_ms=400)
    assert mild.state == DEGRADED, mild.reasons
    assert HealthMonitor("r", expected_interval_ms=100).observe(good, observed_ms=0, now_ms=5000).state == UNSAFE

    # Timestamp regression is reported and does not rewind the high-water mark.
    # The sample must still be fresh, or staleness would mask the regression finding.
    back = HealthMonitor("r", expected_interval_ms=100)
    back.observe(good, observed_ms=5000, now_ms=5000)
    regressed = back.observe(good, observed_ms=4950, now_ms=5000)
    assert regressed.state == DEGRADED and "regression" in " ".join(regressed.reasons), regressed.as_dict()
    assert back.last_observed_ms == 5000, "a regressed sample must not rewind the high-water mark"

    # A flatline needs a full window before it can be claimed.
    flat = HealthMonitor("r", expected_interval_ms=100, window=4)
    states = [flat.observe({"bmi270.accelX": 1.0}, observed_ms=i, now_ms=i).state for i in range(6)]
    assert states[0] == HEALTHY and DEGRADED in states, states

    # A spike trips immediately, and repeated strikes quarantine the channel while others survive.
    spike = HealthMonitor("r", expected_interval_ms=100)
    spike.observe({"bmi270.accelX": 0.0, "sht40.humidityPct": 40.0}, observed_ms=0, now_ms=0)
    for step in range(1, 5):
        report = spike.observe({"bmi270.accelX": 18.0 if step % 2 else -18.0, "sht40.humidityPct": 40.0},
                               observed_ms=step, now_ms=step)
    assert "bmi270.accelX" in report.quarantined, report.as_dict()
    assert "sht40.humidityPct" in report.channels_checked, report.as_dict()
    spike.release_channel("bmi270.accelX")
    assert "bmi270.accelX" not in spike.quarantined

    # Cross-channel disagreement between two sensors that both publish `temperatureC`.
    hot = HealthMonitor("r", expected_interval_ms=100).observe(
        {"sht40.temperatureC": 20.0, "bmi270.temperatureC": 60.0}, observed_ms=1, now_ms=1)
    assert hot.state == DEGRADED and "disagree" in " ".join(hot.reasons)

    # Orientation and magnetic sanity.
    quat = dict(zip(QUATERNION_CHANNELS, (0.5, 0.0, 0.0, 0.0)))
    assert HealthMonitor("r", expected_interval_ms=100).observe(quat, observed_ms=1, now_ms=1).state == UNSAFE
    quat = dict(zip(QUATERNION_CHANNELS, (1.0, 0.0, 0.0, 0.0)))
    assert HealthMonitor("r", expected_interval_ms=100).observe(quat, observed_ms=1, now_ms=1).state == HEALTHY
    strong = dict(zip(MAGNETIC_VECTOR_CHANNELS, (900.0, 0.0, 0.0)))
    assert HealthMonitor("r", expected_interval_ms=100).observe(strong, observed_ms=1, now_ms=1).state == DEGRADED
    earth = dict(zip(MAGNETIC_VECTOR_CHANNELS, (20.0, 30.0, 25.0)))
    assert HealthMonitor("r", expected_interval_ms=100).observe(earth, observed_ms=1, now_ms=1).state == HEALTHY

    # Disconnect is OFFLINE and clears the windows; reconnect restores service.
    gone = HealthMonitor("r", expected_interval_ms=100)
    gone.observe(good, observed_ms=1, now_ms=1)
    gone.note_disconnect()
    assert gone.observe(good, observed_ms=2, now_ms=2).state == OFFLINE
    gone.note_reconnect()
    assert gone.observe(good, observed_ms=3, now_ms=3).state == HEALTHY
    print("cargo.health self-check passed")


if __name__ == "__main__":
    demo()
