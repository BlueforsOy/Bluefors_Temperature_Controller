from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("qcodes")

from bluefors_tc.qcodes_driver import BlueforsTC  # noqa: E402

from .fake_tc import FakeTC  # noqa: E402


@pytest.fixture
def instrument(fake: FakeTC, monkeypatch: pytest.MonkeyPatch) -> Iterator[BlueforsTC]:
    from bluefors_tc import client as client_module

    real_init = client_module.TemperatureController.__init__

    def init(self, host, **kwargs):
        real_init(self, host, http_port=fake.http_port, websocket_port=fake.ws_port, **kwargs)

    monkeypatch.setattr(client_module.TemperatureController, "__init__", init)
    inst = BlueforsTC("tc_test", "127.0.0.1")
    yield inst
    inst.close()


def test_idn(instrument: BlueforsTC) -> None:
    idn = instrument.get_idn()
    assert idn["vendor"] == "Bluefors" and idn["serial"] == "9999"


def test_channels(instrument: BlueforsTC) -> None:
    assert len(instrument.channels) == 8
    assert instrument.ch1.temperature() == pytest.approx(0.0102)
    assert instrument.ch2.resistance() == pytest.approx(120.0)


def test_channel_without_data_raises(instrument: BlueforsTC) -> None:
    with pytest.raises(Exception, match="no measurements"):
        instrument.ch5.temperature()


def test_heater_power_and_setpoint(instrument: BlueforsTC, fake: FakeTC) -> None:
    instrument.heater4.power(1e-6)
    assert instrument.heater4.mode() == "manual"
    assert instrument.heater4.power() == 1e-6

    fake.channels[1]["coupled_heater_nr"] = 4
    instrument.heater4.setpoint(0.3)
    assert instrument.heater4.mode() == "pid"
    assert instrument.heater4.setpoint() == 0.3

    instrument.heater4.active(False)
    assert instrument.heater4.active() is False


def test_power_validator(instrument: BlueforsTC) -> None:
    with pytest.raises(ValueError):
        instrument.heater4.power(2)


def test_parameters_and_submodules_are_typed_attributes(instrument: BlueforsTC) -> None:
    from qcodes.instrument import ChannelTuple
    from qcodes.parameters import Parameter

    assert isinstance(instrument.channels, ChannelTuple)
    assert isinstance(instrument.heaters, ChannelTuple)
    assert instrument.channels[0] is instrument.ch1
    assert instrument.heaters[3] is instrument.heater4
    # the attribute and the registered parameter are the same object
    assert isinstance(instrument.ch1.temperature, Parameter)
    assert instrument.ch1.temperature is instrument.ch1.parameters["temperature"]
    assert instrument.heater4.setpoint is instrument.heater4.parameters["setpoint"]


def test_connect_message_can_be_turned_off(
    fake: FakeTC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from bluefors_tc import client as client_module

    real_init = client_module.TemperatureController.__init__

    def init(self, host, **kwargs):
        real_init(self, host, http_port=fake.http_port, websocket_port=fake.ws_port, **kwargs)

    monkeypatch.setattr(client_module.TemperatureController, "__init__", init)
    inst = BlueforsTC("tc_quiet", "127.0.0.1", print_connect_message=False)
    try:
        assert "Connected to" not in capsys.readouterr().out
    finally:
        inst.close()


def test_snapshot_does_not_read_measurements(instrument: BlueforsTC, fake: FakeTC) -> None:
    # channel 5 has no data; a snapshot must not try to read it
    fake.requests.clear()
    snapshot = instrument.snapshot(update=None)
    assert "ch5" in snapshot["submodules"]
    assert not any(path == "channel/historical-data" for _, path, _ in fake.requests)
