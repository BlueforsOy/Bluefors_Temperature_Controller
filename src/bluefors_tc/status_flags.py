"""Measurement status flags reported in ``status_flags``.

Source: Bluefors Temperature Controller API Technical Reference, version 3.0,
table of measurement error and warning codes.
"""

from __future__ import annotations

from typing import NamedTuple


class StatusFlag(NamedTuple):
    """One decoded entry of a measurement's ``status_flags`` list."""

    code: int
    severity: str  # "error", "warning" or "notification"
    name: str
    description: str

    def __str__(self) -> str:
        return f"{self.code} {self.name} ({self.severity})"


_KNOWN = {
    200: ("error", "No data", "Not getting data from the measurement hardware."),
    241: ("error", "Signal too noisy", "High resistance; check the sensor connection."),
    242: ("error", "Overflow", "Saturated measurement; resistance above the excitation range."),
    243: ("error", "Common mode overflow", "Grounding problem or noisy ground."),
    244: ("error", "Zero measured value", "Device fault or short circuit."),
    245: ("error", "Resistance too high", "Resistance is above the maximum range."),
    246: ("error", "Resistance too low", "Resistance is below the minimum range."),
    247: ("error", "Unreliable data", "The signal arrived later than expected."),
    511: ("warning", "Temperature below range", "Below the impedance-temperature curve."),
    512: ("warning", "Temperature above range", "Above the programmed curve."),
    514: ("warning", "Temperature below calibration range", ""),
    515: ("warning", "Temperature above calibration range", ""),
    518: ("warning", "Temperature data unreliable", "The calculated temperature is negative."),
    519: ("warning", "No calibration curve", "No calibration curve is set for the channel."),
    521: ("warning", "Resistance below range", "Below the calibration range."),
    522: ("warning", "Resistance above range", "Above the calibration range."),
    901: ("notification", "Vmax auto-ranging", "Excitation was tuned under Vmax."),
}


def describe(code: int) -> StatusFlag:
    """Return the decoded flag for ``code``; unknown codes are classified by range."""
    if code in _KNOWN:
        return StatusFlag(code, *_KNOWN[code])
    if 200 <= code < 500:
        severity = "error"
    elif 500 <= code < 900:
        severity = "warning"
    else:
        severity = "notification"
    return StatusFlag(code, severity, "Unknown status", "Not listed in the API reference.")
