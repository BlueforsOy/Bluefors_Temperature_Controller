"""Tests against a real Temperature Controller.

Read-only tests:

    pytest -m live --tc-host 192.168.1.10

Heater write tests (heater 4 by default; its settings are restored afterwards):

    pytest -m live --tc-host 192.168.1.10 --tc-allow-writes --tc-heater 4

Only run write tests on a controller that is not regulating a cryostat.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bluefors_tc import TCRequestError, TemperatureController

pytestmark = pytest.mark.live

_RESTORE_KEYS = (
    "heater_nr",
    "active",
    "name",
    "pid_mode",
    "resistance",
    "power",
    "target_temperature",
    "target_temperature_shown",
    "control_algorithm",
    "control_algorithm_settings",
    "setpoint",
    "max_power",
)


@pytest.fixture(scope="module")
def live(request: pytest.FixtureRequest) -> Iterator[TemperatureController]:
    with TemperatureController(request.config.getoption("--tc-host")) as tc:
        yield tc


def test_system(live: TemperatureController) -> None:
    info = live.system()
    assert info.serial and info.software_version


def test_measuring(live: TemperatureController) -> None:
    assert live.statemachine().measuring


def test_latest_of_every_active_channel(live: TemperatureController) -> None:
    active = [c.channel_nr for c in live.channels() if c.active]
    assert active, "no active channels"
    for channel_nr in active:
        assert live.latest_measurement(channel_nr).channel_nr == channel_nr


def test_next_measurement(live: TemperatureController) -> None:
    channel_nr = next(c.channel_nr for c in live.channels() if c.active)
    m = live.next_measurement(channel_nr, timeout=300)
    assert m.channel_nr == channel_nr and m.status_flags is not None


def test_history(live: TemperatureController) -> None:
    from datetime import timedelta

    channel_nr = next(c.channel_nr for c in live.channels() if c.active)
    assert len(live.channel_history(channel_nr, start=timedelta(hours=1))) > 0


def test_rejected_request(live: TemperatureController) -> None:
    with pytest.raises(TCRequestError):
        live.request("heater", {"heater_nr": 7})


@pytest.fixture
def heater_nr(request: pytest.FixtureRequest, live: TemperatureController) -> Iterator[int]:
    nr = request.config.getoption("--tc-heater")
    saved = live.request("heater", {"heater_nr": nr})
    yield nr
    live.request("heater/update", {k: saved[k] for k in _RESTORE_KEYS if k in saved})
    restored = live.request("heater", {"heater_nr": nr})
    assert {k: restored.get(k) for k in _RESTORE_KEYS} == {k: saved.get(k) for k in _RESTORE_KEYS}


@pytest.mark.live_write
def test_manual_power(live: TemperatureController, heater_nr: int) -> None:
    heater = live.set_heater_power(heater_nr, 1e-6)
    assert heater.mode == "manual" and heater.power == 1e-6
    assert live.heater(heater_nr).power == 1e-6


@pytest.mark.live_write
@pytest.mark.parametrize("setpoint", [0.05, 0.3])
def test_pid_setpoint(live: TemperatureController, heater_nr: int, setpoint: float) -> None:
    coupled = [c for c in live.channels(include_internal=True) if c.coupled_heater_nr == heater_nr]
    if not coupled:
        pytest.skip(f"no channel coupled to heater {heater_nr}")
    heater = live.set_pid(heater_nr, setpoint)
    assert heater.mode == "pid" and heater.setpoint == setpoint


@pytest.mark.live_write
def test_heater_off(live: TemperatureController, heater_nr: int) -> None:
    assert live.heater_off(heater_nr).active is False
