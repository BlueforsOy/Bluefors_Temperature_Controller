"""Typed views of the JSON objects returned by the Temperature Controller.

Every model keeps the full decoded reply in ``raw``, so fields that are not
mapped here are still available.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import floor, log10
from pathlib import Path
from typing import Any, Optional, Union

from .status_flags import StatusFlag, describe

SAMPLE_CHANNELS = tuple(range(1, 9))
"""Channels 1-8: the sample (thermometer) inputs."""

INTERNAL_CHANNELS = tuple(range(9, 13))
"""Channels 9-12: built-in reference resistors (10 kOhm, 1 kOhm, 100 Ohm, 10 Ohm)."""

HEATERS = tuple(range(1, 5))


_SI_PREFIXES = {-9: "n", -6: "µ", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}


def _engineering(value: float, unit: str, max_exponent: int = 9, digits: int = 5) -> str:
    """Five significant digits with an SI prefix, as the Temperature Controller UI shows."""
    if value == 0:
        return f"{0:.{digits - 1}f} {unit}"
    exponent = min(max_exponent, max(-9, floor(log10(abs(value)) / 3) * 3))
    text = f"{value / 10**exponent:#.{digits}g}".rstrip(".")
    if abs(float(text)) >= 1000 and exponent < max_exponent:  # rounding carried a digit
        exponent += 3
        text = f"{value / 10**exponent:#.{digits}g}".rstrip(".")
    return f"{text} {_SI_PREFIXES[exponent]}{unit}"


def format_temperature(kelvin: Optional[float]) -> str:
    """Format a temperature like the UI: ``12.345 mK``, ``4.2150 K``, ``273.28 K``."""
    return "n/a" if kelvin is None else _engineering(kelvin, "K", max_exponent=0)


def format_resistance(ohms: Optional[float]) -> str:
    """Format a resistance like the UI: ``100.01 Ohm``, ``18.300 kOhm``."""
    return "n/a" if ohms is None else _engineering(ohms, "Ohm")


def format_power(watts: Optional[float]) -> str:
    """Format a heater power: ``100.00 µW``, ``6.3353 nW``, ``3.0000 mW``."""
    if watts is None:
        return "n/a"
    if 0 < abs(watts) < 1e-9:  # picowatts are below the nano prefix
        return f"{watts * 1e12:#.5g}".rstrip(".") + " pW"
    return _engineering(watts, "W", max_exponent=0)


def _float(value: Any) -> Optional[float]:
    return None if value is None or value == "" else float(value)


def _utc(timestamp: Optional[float]) -> Optional[datetime]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)


@dataclass(frozen=True)
class SystemInfo:
    serial: str
    label: str
    software_version: str
    api_version: Optional[int]
    raw: dict[str, Any] = field(repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SystemInfo:
        return cls(
            serial=str(data.get("serial", "")),
            label=str(data.get("label", "")),
            software_version=str(data.get("software_version", "")),
            api_version=data.get("api_version"),
            raw=data,
        )


@dataclass(frozen=True)
class StateMachine:
    state: str
    measuring: bool
    channel_nr: Optional[int]
    raw: dict[str, Any] = field(repr=False, compare=False)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> StateMachine:
        return cls(
            state=str(data.get("state", "")),
            measuring=bool(data.get("measuring", False)),
            channel_nr=data.get("channel_nr"),
            raw=data,
        )


@dataclass(frozen=True)
class Channel:
    channel_nr: int
    name: str
    active: bool
    calib_curve_nr: Optional[int]
    coupled_heater_nr: int
    raw: dict[str, Any] = field(repr=False, compare=False)

    @property
    def is_internal(self) -> bool:
        """True for channels 9-12, the built-in reference resistors."""
        return self.channel_nr in INTERNAL_CHANNELS

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Channel:
        return cls(
            channel_nr=int(data["channel_nr"]),
            name=str(data.get("name", "")),
            active=bool(data.get("active", False)),
            calib_curve_nr=data.get("calib_curve_nr"),
            coupled_heater_nr=int(data.get("coupled_heater_nr") or 0),
            raw=data,
        )


@dataclass(frozen=True)
class Heater:
    heater_nr: int
    name: str
    active: bool
    pid_mode: bool
    power: Optional[float]
    max_power: Optional[float]
    setpoint: Optional[float]
    resistance: Optional[float]
    proportional: Optional[float]
    integral: Optional[float]
    derivative: Optional[float]
    raw: dict[str, Any] = field(repr=False, compare=False)

    @property
    def mode(self) -> str:
        """``"pid"`` (closed loop) or ``"manual"`` (fixed power)."""
        return "pid" if self.pid_mode else "manual"

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Heater:
        pid = data.get("control_algorithm_settings") or {}
        return cls(
            heater_nr=int(data["heater_nr"]),
            name=str(data.get("name", "")),
            active=bool(data.get("active", False)),
            pid_mode=data.get("pid_mode") == 1,
            power=_float(data.get("power")),
            max_power=_float(data.get("max_power")),
            setpoint=_float(data.get("setpoint")),
            resistance=_float(data.get("resistance")),
            proportional=_float(pid.get("proportional")),
            integral=_float(pid.get("integral")),
            derivative=_float(pid.get("derivative")),
            raw=data,
        )


@dataclass(frozen=True)
class Measurement:
    """One measurement of one channel.

    ``temperature`` is ``None`` when the channel has no calibration curve or the
    reading is invalid; check ``flags`` for the reason. ``display_value``
    then falls back to the resistance, as the UI does. ``status_flags`` is
    ``None`` when the source did not include flags (historical data does not).
    """

    channel_nr: int
    timestamp: Optional[datetime]
    temperature: Optional[float]
    resistance: Optional[float]
    reactance: Optional[float]
    status_flags: Optional[tuple[int, ...]]
    raw: dict[str, Any] = field(repr=False, compare=False)

    @property
    def flags(self) -> tuple[StatusFlag, ...]:
        return tuple(describe(code) for code in self.status_flags or ())

    @property
    def has_error(self) -> bool:
        return any(f.severity == "error" for f in self.flags)

    @property
    def has_warning(self) -> bool:
        return any(f.severity == "warning" for f in self.flags)

    @property
    def display_value(self) -> str:
        """The value the Temperature Controller UI would show.

        The temperature when there is one, otherwise the resistance: for
        example when the channel has no calibration curve, or the resistance
        is outside the curve.
        """
        if self.temperature is not None:
            return format_temperature(self.temperature)
        return format_resistance(self.resistance)

    def __str__(self) -> str:
        text = f"Channel {self.channel_nr}: {self.display_value}"
        if self.temperature is not None and self.resistance is not None:
            text += f", R = {format_resistance(self.resistance)}"
        if self.flags:
            text += " [" + "; ".join(str(f) for f in self.flags) + "]"
        return text

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Measurement:
        flags = data.get("status_flags")
        return cls(
            channel_nr=int(data["channel_nr"]),
            timestamp=_utc(data.get("timestamp")),
            temperature=_float(data.get("temperature")),
            resistance=_float(data.get("resistance")),
            reactance=_float(data.get("reactance")),
            status_flags=None if flags is None else tuple(int(c) for c in flags),
            raw=data,
        )


@dataclass(frozen=True)
class History:
    """Historical data for one channel or heater, as columns.

    ``columns`` maps each requested field to a list of values, for example
    ``{"timestamp": [...], "temperature": [...]}``. Timestamps are Unix time in
    seconds (UTC).
    """

    columns: dict[str, list[Any]]
    raw: dict[str, Any] = field(repr=False, compare=False)

    def __len__(self) -> int:
        return max((len(v) for v in self.columns.values()), default=0)

    def __getitem__(self, name: str) -> list[Any]:
        return self.columns[name]

    @property
    def times(self) -> list[datetime]:
        """The ``timestamp`` column as timezone-aware UTC datetimes."""
        return [
            datetime.fromtimestamp(t, tz=timezone.utc) for t in self.columns.get("timestamp", [])
        ]

    def rows(self) -> list[dict[str, Any]]:
        """The data as one dictionary per sample."""
        names = list(self.columns)
        rows = zip(*self.columns.values(), strict=False)  # stops at the shortest column
        return [dict(zip(names, values, strict=True)) for values in rows]

    def to_csv(self, path: Union[str, Path]) -> Path:
        """Write the data to a CSV file, one row per sample, and return its path."""
        path = Path(path)
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.columns))
            writer.writeheader()
            writer.writerows(self.rows())
        return path

    def to_dataframe(self) -> Any:
        """Return a pandas DataFrame (requires pandas)."""
        import pandas as pd

        frame = pd.DataFrame(self.columns)
        if "timestamp" in frame:
            frame["time"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        return frame
