from __future__ import annotations

from collections.abc import Iterator

import pytest

from bluefors_tc import TemperatureController

from .fake_tc import FakeTC


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("bluefors-tc live tests")
    group.addoption("--tc-host", help="run live tests against this Temperature Controller")
    group.addoption(
        "--tc-allow-writes",
        action="store_true",
        help="allow live tests that change heater settings (restored afterwards)",
    )
    group.addoption("--tc-heater", type=int, default=4, help="heater used by live write tests")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    host = config.getoption("--tc-host")
    writes = config.getoption("--tc-allow-writes")
    for item in items:
        if "live" in item.keywords and not host:
            item.add_marker(pytest.mark.skip(reason="needs --tc-host"))
        if "live_write" in item.keywords and not writes:
            item.add_marker(pytest.mark.skip(reason="needs --tc-allow-writes"))


@pytest.fixture
def fake() -> Iterator[FakeTC]:
    server = FakeTC().start()
    yield server
    server.stop()


@pytest.fixture
def tc(fake: FakeTC) -> Iterator[TemperatureController]:
    client = TemperatureController(
        "127.0.0.1", http_port=fake.http_port, websocket_port=fake.ws_port, timeout=5
    )
    yield client
    client.close()
