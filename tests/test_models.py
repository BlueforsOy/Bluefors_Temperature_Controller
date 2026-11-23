from __future__ import annotations

import csv
from pathlib import Path

from bluefors_tc import (
    History,
    Measurement,
    describe,
    format_power,
    format_resistance,
    format_temperature,
)


def test_format_temperature() -> None:
    assert format_temperature(0.0123) == "12.300 mK"
    assert format_temperature(4.2) == "4.2000 K"
    assert format_temperature(273.2647) == "273.26 K"
    assert format_temperature(999.996) == "1000.0 K"  # never "kK"
    assert format_temperature(0.00099999) == "999.99 µK"
    assert format_temperature(0) == "0.0000 K"
    assert format_temperature(None) == "n/a"


def test_format_resistance() -> None:
    assert format_resistance(100.013) == "100.01 Ohm"
    assert format_resistance(1000.353) == "1.0004 kOhm"
    assert format_resistance(999999.9) == "1.0000 MOhm"  # rounding moves to the next prefix
    assert format_resistance(0.5) == "500.00 mOhm"
    assert format_resistance(None) == "n/a"


def test_format_power() -> None:
    assert format_power(100e-6) == "100.00 µW"
    assert format_power(6.3353e-9) == "6.3353 nW"
    assert format_power(7.308e-11) == "73.080 pW"
    assert format_power(3e-3) == "3.0000 mW"
    assert format_power(0.5) == "500.00 mW"
    assert format_power(0) == "0.0000 W"
    assert format_power(None) == "n/a"


def test_display_value_falls_back_to_resistance() -> None:
    calibrated = Measurement.from_api(
        {"channel_nr": 1, "temperature": 0.012345, "resistance": 18300.0, "status_flags": []}
    )
    assert calibrated.display_value == "12.345 mK"
    assert str(calibrated) == "Channel 1: 12.345 mK, R = 18.300 kOhm"
    for flag in (519, 512):  # no calibration curve; above the curve
        m = Measurement.from_api(
            {"channel_nr": 5, "temperature": None, "resistance": 100.013, "status_flags": [flag]}
        )
        assert m.display_value == "100.01 Ohm"
        assert str(m).startswith("Channel 5: 100.01 Ohm [")


def test_measurement_str_and_flags() -> None:
    m = Measurement.from_api(
        {
            "channel_nr": 2,
            "temperature": None,
            "resistance": 1000.35,
            "timestamp": 0,
            "status_flags": [519, 242],
        }
    )
    assert m.has_error and m.has_warning
    assert str(m) == (
        "Channel 2: 1.0004 kOhm [519 No calibration curve (warning); 242 Overflow (error)]"
    )


def test_unknown_flag_is_classified_by_range() -> None:
    assert describe(299).severity == "error"
    assert describe(599).severity == "warning"
    assert describe(999).severity == "notification"


def test_history_rows_and_csv(tmp_path: Path) -> None:
    h = History(columns={"timestamp": [1.0, 2.0], "temperature": [0.1, 0.2]}, raw={})
    assert len(h) == 2
    assert h.rows() == [
        {"timestamp": 1.0, "temperature": 0.1},
        {"timestamp": 2.0, "temperature": 0.2},
    ]
    path = h.to_csv(tmp_path / "out.csv")
    with path.open() as f:
        assert list(csv.DictReader(f))[1] == {"timestamp": "2.0", "temperature": "0.2"}
