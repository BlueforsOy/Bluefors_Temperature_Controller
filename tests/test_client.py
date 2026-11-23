from __future__ import annotations

import errno
import time
import warnings
from datetime import timedelta
from typing import Any

import pytest
import requests

from bluefors_tc import (
    TCConnectionError,
    TCNoDataError,
    TCRequestError,
    TCTimeoutError,
    TCWarning,
    TemperatureController,
)
from bluefors_tc import client as client_module

from .fake_tc import FakeTC


def last_body(fake: FakeTC, path: str) -> dict:
    return [body for _, p, body in fake.requests if p == path][-1]


@pytest.mark.parametrize(
    "address", ["192.168.1.10", "http://192.168.1.10:5001/", " 192.168.1.10 ", "ws://192.168.1.10"]
)
def test_host_accepts_pasted_urls(address: str) -> None:
    assert TemperatureController(address).host == "192.168.1.10"


def test_system(tc: TemperatureController) -> None:
    info = tc.system()
    assert info.serial == "9999"
    assert info.api_version == 2


def test_channels_default_to_sample_channels(tc: TemperatureController) -> None:
    assert [c.channel_nr for c in tc.channels()] == list(range(1, 9))
    all_channels = tc.channels(include_internal=True)
    assert len(all_channels) == 12
    assert all(c.is_internal for c in all_channels[8:])


def test_latest_measurement_any_channel_has_flags(tc: TemperatureController) -> None:
    m = tc.latest_measurement()
    assert m.channel_nr == 3
    assert m.status_flags == (519,)
    assert m.has_warning and not m.has_error
    assert m.temperature is None


def test_latest_measurement_of_channel_uses_newest_history_point(
    tc: TemperatureController, fake: FakeTC
) -> None:
    m = tc.latest_measurement(1)
    assert m.temperature == pytest.approx(0.0102)
    assert m.status_flags is None
    body = last_body(fake, "channel/historical-data")
    assert body["start_time"].endswith("Z") and body["stop_time"].endswith("Z")


def test_latest_measurement_without_data_raises(tc: TemperatureController) -> None:
    with pytest.raises(TCNoDataError, match="Channel 5"):
        tc.latest_measurement(5)


def test_next_measurement_waits_for_channel(tc: TemperatureController) -> None:
    m = tc.next_measurement(2, timeout=5)
    assert m.channel_nr == 2
    assert m.status_flags == ()
    assert m.temperature == pytest.approx(0.02)


def test_next_measurement_of_inactive_channel_times_out(tc: TemperatureController) -> None:
    start = time.monotonic()
    with pytest.raises(TCTimeoutError, match="channel 7"):
        tc.next_measurement(7, timeout=1)
    assert time.monotonic() - start < 3


def test_stream_stops_after_duration_and_closes(tc: TemperatureController, fake: FakeTC) -> None:
    seen = [m.channel_nr for m in tc.stream_measurements([1, 3], duration=0.5)]
    assert seen and set(seen) <= {1, 3}
    time.sleep(0.3)
    assert fake.listen_open == 0


def test_stream_raises_when_nothing_arrives(tc: TemperatureController, fake: FakeTC) -> None:
    for c in fake.channels.values():
        c["active"] = False
    with pytest.raises(TCTimeoutError, match="measuring"):
        next(iter(tc.stream_measurements(idle_timeout=0.5)))


def test_channel_history_with_timedelta(tc: TemperatureController) -> None:
    history = tc.channel_history(1, start=timedelta(minutes=10))
    assert len(history) == 2
    assert history.rows()[0].keys() == {"timestamp", "temperature", "resistance"}
    assert history.times[0].tzinfo is not None


def test_heater_history(tc: TemperatureController) -> None:
    history = tc.heater_history(4, start=timedelta(hours=1))
    assert history["power"] == [0.0005]


def test_set_heater_power(tc: TemperatureController, fake: FakeTC) -> None:
    heater = tc.set_heater_power(4, 1e-6)
    assert last_body(fake, "heater/update") == {
        "heater_nr": 4,
        "active": True,
        "pid_mode": 0,
        "power": 1e-6,
    }
    assert heater.mode == "manual" and heater.active and heater.power == 1e-6


@pytest.mark.parametrize("power", [-1e-6, 1.5])
def test_set_heater_power_rejects_out_of_range(
    tc: TemperatureController, fake: FakeTC, power: float
) -> None:
    with pytest.raises(ValueError):
        tc.set_heater_power(4, power)
    assert not any(p == "heater/update" for _, p, _ in fake.requests)


def test_set_pid_requires_coupled_channel(tc: TemperatureController, fake: FakeTC) -> None:
    with pytest.raises(ValueError, match="channel_nr"):
        tc.set_pid(4, 0.05)
    assert not any(p == "heater/update" for _, p, _ in fake.requests)


@pytest.mark.parametrize("setpoint", [0.0, 0.01, 0.08, 0.1, 0.3, 0.5, 0.6, 1.5, 300.0])
def test_set_pid_any_setpoint(tc: TemperatureController, fake: FakeTC, setpoint: float) -> None:
    # The original example driver failed for 80-500 mK; this must work everywhere.
    heater = tc.set_pid(4, setpoint, channel_nr=1)
    assert fake.channels[1]["coupled_heater_nr"] == 4
    assert last_body(fake, "heater/update") == {
        "heater_nr": 4,
        "active": True,
        "pid_mode": 1,
        "setpoint": setpoint,
    }
    assert heater.mode == "pid"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_power": 5.0},
        {"max_power": -1e-6},
        {"proportional": "high"},
        {"proportional": float("nan")},
        {"integral": float("inf")},
        {"max_power": float("nan")},
        {"channel_nr": 13},
    ],
)
def test_set_pid_rejects_bad_arguments_before_sending(
    tc: TemperatureController, fake: FakeTC, kwargs: dict
) -> None:
    kwargs.setdefault("channel_nr", 2)
    with pytest.raises(ValueError):
        tc.set_pid(4, 0.05, **kwargs)
    assert fake.requests == []
    assert all(c["coupled_heater_nr"] == 0 for c in fake.channels.values())


def test_set_pid_on_calibrated_channel_does_not_warn(tc: TemperatureController) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tc.set_pid(4, 0.05, channel_nr=1)


@pytest.mark.parametrize("coupled", [False, True])
def test_set_pid_warns_when_channel_has_no_temperature(
    tc: TemperatureController, fake: FakeTC, coupled: bool
) -> None:
    fake.history[3] = [(time.time() - 30, None, 1500.0)]  # no calibration curve
    if coupled:
        fake.channels[3]["coupled_heater_nr"] = 4
    with pytest.warns(TCWarning, match="channel 3 measures no temperature"):
        tc.set_pid(4, 0.05, channel_nr=None if coupled else 3)
    assert last_body(fake, "heater/update")["setpoint"] == 0.05  # still applied


def test_set_pid_is_sent_when_the_temperature_check_fails(
    tc: TemperatureController, fake: FakeTC, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_handle = fake.handle

    def handle(method: str, path: str, body: Any) -> tuple[int, Any]:
        if path == "channel/historical-data":
            return 400, {"status": "ERROR", "error_msg": "history unavailable"}
        return real_handle(method, path, body)

    monkeypatch.setattr(fake, "handle", handle)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        tc.set_pid(4, 0.05, channel_nr=1)
    assert last_body(fake, "heater/update")["setpoint"] == 0.05


def test_set_pid_warns_when_channel_has_no_data(tc: TemperatureController, fake: FakeTC) -> None:
    with pytest.warns(TCWarning, match="channel 5 has no measurements"):
        tc.set_pid(4, 0.05, channel_nr=5)


def test_set_pid_merges_partial_gains(tc: TemperatureController, fake: FakeTC) -> None:
    fake.channels[1]["coupled_heater_nr"] = 4
    tc.set_pid(4, 0.05, proportional=0.2, max_power=1e-4)
    body = last_body(fake, "heater/update")
    assert body["control_algorithm_settings"] == {
        "proportional": 0.2,
        "integral": 100,
        "derivative": 0,
    }
    assert body["max_power"] == 1e-4


def test_heater_off(tc: TemperatureController, fake: FakeTC) -> None:
    tc.heater_off(2)
    assert last_body(fake, "heater/update") == {"heater_nr": 2, "active": False}


def test_rejected_request_raises_with_controller_message(tc: TemperatureController) -> None:
    with pytest.raises(TCRequestError, match="greater than the maximum of 4") as info:
        tc.request("heater/update", {"heater_nr": 7})
    assert info.value.endpoint == "heater/update"


def test_spec_style_error_object_is_understood() -> None:
    err = TCRequestError.from_response(
        "x", None, {"status": "ERROR", "error": {"code": 3, "message": "Bad", "details": "why"}}
    )
    assert err.message == "Bad why (code 3)"


def test_unknown_endpoint(tc: TemperatureController) -> None:
    with pytest.raises(TCRequestError, match="unknown endpoint"):
        tc.request("no/such/endpoint")


def test_invalid_numbers_are_caught_before_sending(tc: TemperatureController) -> None:
    with pytest.raises(ValueError):
        tc.heater(5)
    with pytest.raises(ValueError):
        tc.channel(13)
    with pytest.raises(ValueError):
        tc.set_pid(4, -0.001, channel_nr=1)


def test_connection_refused_names_the_cause() -> None:
    with TemperatureController("127.0.0.1", http_port=1, websocket_port=1, timeout=2) as tc:
        with pytest.raises(TCConnectionError, match="Connection refused.*nothing is listening"):
            tc.system()
        with pytest.raises(TCConnectionError, match="WebSocket.*Connection refused"):
            tc.next_measurement(1, timeout=1)


def test_unresolvable_host_names_the_cause() -> None:
    tc = TemperatureController("no-such-tc.invalid", timeout=5)
    with pytest.raises(TCConnectionError, match="could not be resolved"):
        tc.system()
    tc.close()


@pytest.mark.parametrize("platform, mentions_local_network", [("darwin", True), ("linux", False)])
def test_no_route_to_host_hint(
    monkeypatch: pytest.MonkeyPatch, platform: str, mentions_local_network: bool
) -> None:
    # requests wraps the socket error: ConnectionError -> MaxRetryError.reason -> OSError
    os_error = OSError(errno.EHOSTUNREACH, "No route to host")
    wrapped = type("MaxRetryError", (Exception,), {})("pool")
    wrapped.reason = type("NewConnectionError", (Exception,), {})("conn")
    wrapped.reason.__cause__ = os_error
    exc = requests.ConnectionError(wrapped)
    assert client_module._root_cause(exc) is os_error

    monkeypatch.setattr(client_module.sys, "platform", platform)
    text = client_module._connection_problem(exc, 5001)
    assert text.startswith("No route to host. There is no network path")
    assert ("Local Network" in text) is mentions_local_network
