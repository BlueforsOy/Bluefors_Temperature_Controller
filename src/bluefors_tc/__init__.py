"""Python client for the Bluefors Temperature Controller.

Quick start::

    from bluefors_tc import TemperatureController

    with TemperatureController("192.168.1.10") as tc:
        print(tc.system())
        print(tc.latest_measurement(1))
"""

from .client import HTTP_PORT, WEBSOCKET_PORT, TemperatureController
from .exceptions import (
    TCConnectionError,
    TCError,
    TCNoDataError,
    TCRequestError,
    TCTimeoutError,
    TCWarning,
)
from .models import (
    HEATERS,
    INTERNAL_CHANNELS,
    SAMPLE_CHANNELS,
    Channel,
    Heater,
    History,
    Measurement,
    StateMachine,
    SystemInfo,
    format_power,
    format_resistance,
    format_temperature,
)
from .status_flags import StatusFlag, describe

__version__ = "0.1.1"

__all__ = [
    "HEATERS",
    "HTTP_PORT",
    "INTERNAL_CHANNELS",
    "SAMPLE_CHANNELS",
    "WEBSOCKET_PORT",
    "Channel",
    "Heater",
    "History",
    "Measurement",
    "StateMachine",
    "StatusFlag",
    "SystemInfo",
    "TCConnectionError",
    "TCError",
    "TCNoDataError",
    "TCRequestError",
    "TCTimeoutError",
    "TCWarning",
    "TemperatureController",
    "describe",
    "format_power",
    "format_resistance",
    "format_temperature",
]
