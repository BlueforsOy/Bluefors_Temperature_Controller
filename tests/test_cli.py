from __future__ import annotations

import pytest

from bluefors_tc import cli
from bluefors_tc.client import TemperatureController

from .fake_tc import FakeTC


@pytest.fixture
def run(fake: FakeTC, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    real_init = TemperatureController.__init__

    def init(self, host, **kwargs):
        real_init(self, host, http_port=fake.http_port, websocket_port=fake.ws_port, **kwargs)

    monkeypatch.setattr(TemperatureController, "__init__", init)

    def _run(*argv: str) -> tuple[int, str, str]:
        code = cli.main(["--host", "127.0.0.1", *argv])
        out, err = capsys.readouterr()
        return code, out, err

    return _run


def test_info(run) -> None:
    code, out, _ = run("info")
    assert code == 0
    assert "Serial number:    9999" in out
    assert "Measuring:        yes (channel 1)" in out


def test_read_active_channels(run) -> None:
    code, out, _ = run("read")
    assert code == 0
    assert "Channel 1: 10.200 mK" in out
    assert (
        "Channel 3: no measurements in the last 60 minutes" in out
    )  # active but no history in the fake


def test_channels_and_heaters(run) -> None:
    assert "Channel 8" in run("channels")[1]
    assert "Channel 12" in run("channels", "--all")[1]
    assert "Heater 4" in run("heaters")[1]


def test_heaters_show_only_the_setting_of_the_current_mode(run, fake: FakeTC) -> None:
    fake.heaters[3].update(pid_mode=0, power=0.002)
    fake.heaters[4].update(pid_mode=1, power=0.002, setpoint=0.05)
    lines = {line.split()[0]: line for line in run("heaters")[1].splitlines()[1:]}
    assert "2.0000 mW" in lines["3"] and " -  Heater 3" in lines["3"]  # no setpoint
    assert "2.0000 mW" not in lines["4"] and "50.000 mK" in lines["4"]


def test_watch(run) -> None:
    code, out, _ = run("watch", "2", "--duration", "0.3")
    assert code == 0
    assert "Channel 2: 20.000 mK" in out


def test_missing_host(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("BLUEFORS_TC_HOST", raising=False)
    assert cli.main(["info"]) == 2
    assert "BLUEFORS_TC_HOST" in capsys.readouterr().err
