"""Client for the Bluefors Temperature Controller external API.

Request-response calls use HTTP (port 5001). Live measurement streams use
WebSocket (port 5002). Both are described in the Bluefors Temperature
Controller API Technical Reference.
"""

from __future__ import annotations

import errno
import json
import math
import socket
import sys
import time
import warnings
from collections.abc import Iterable, Iterator, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
from urllib.parse import urlsplit

import requests
import websocket

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
    SAMPLE_CHANNELS,
    Channel,
    Heater,
    History,
    Measurement,
    StateMachine,
    SystemInfo,
)

HTTP_PORT = 5001
WEBSOCKET_PORT = 5002

TimeSpec = Union[datetime, timedelta, str]

_MEASUREMENT_FIELDS = ("timestamp", "temperature", "resistance", "reactance")


def _host_only(address: str) -> str:
    """Accept ``192.168.1.10``, ``tc.example.org`` or a pasted ``http://...`` URL."""
    address = address.strip()
    if "//" not in address:
        address = "//" + address
    host = urlsplit(address).hostname
    if not host:
        raise ValueError(f"Not a host name or IP address: {address!r}")
    return host


def _root_cause(exc: BaseException) -> BaseException:
    """The innermost error behind ``exc``, usually the operating system's OSError.

    requests and websocket-client wrap socket errors several levels deep, in
    ``__cause__``, ``__context__``, ``reason`` or ``args``.
    """
    seen: set[int] = set()
    stack = [exc]
    found: BaseException = exc
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, OSError) and (current.errno or current.strerror):
            found = current  # keep the deepest one with an OS error code
        nested = [current.__cause__, current.__context__, getattr(current, "reason", None)]
        nested += [a for a in getattr(current, "args", ()) if isinstance(a, BaseException)]
        stack.extend(n for n in nested if isinstance(n, BaseException))
    return found


def _connection_problem(exc: BaseException, port: int) -> str:
    """Say what went wrong in plain words, for example ``No route to host``, plus a hint."""
    cause = _root_cause(exc)
    if isinstance(cause, socket.gaierror):
        return (
            f"the host name could not be resolved ({cause.strerror or cause}). "
            "Check the name, or use the IP address shown in the controller's network settings."
        )
    code = getattr(cause, "errno", None)
    reason = getattr(cause, "strerror", None) or str(cause) or type(cause).__name__
    if code == errno.ECONNREFUSED:
        hint = (
            f"The address answered, but nothing is listening on port {port}: the controller "
            "may still be starting up, the port may be wrong, or this is not a Temperature "
            "Controller."
        )
    elif code in (errno.EHOSTUNREACH, errno.ENETUNREACH):
        hint = "There is no network path to the controller: check the address and the network."
        if sys.platform == "darwin":
            hint += (
                " On macOS, also check that the app you run Python from is allowed in "
                "System Settings > Privacy & Security > Local Network."
            )
    elif code in (errno.ETIMEDOUT, errno.ECONNRESET):
        hint = "Check the network connection and that the controller is switched on."
    else:
        hint = (
            "Check the address, the network connection, and that the Temperature Controller "
            "is switched on."
        )
    return f"{reason}. {hint}"


def _api_time(value: Optional[TimeSpec], now: datetime) -> str:
    """Convert to the API's UTC ``YYYY-MM-DDTHH:MM:SSZ`` form.

    A ``timedelta`` means "this long before now". A naive ``datetime`` is taken
    as the computer's local time. A string is passed through unchanged.
    """
    if value is None:
        moment = now
    elif isinstance(value, str):
        return value
    elif isinstance(value, timedelta):
        moment = now - value
    else:
        moment = value if value.tzinfo else value.astimezone()
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_number(name: str, value: float, low: float, high: float) -> float:
    value = float(value)
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low} and {high}, got {value}")
    return value


def _check_heater(heater_nr: int) -> int:
    if heater_nr not in HEATERS:
        raise ValueError(f"heater_nr must be 1-4, got {heater_nr}")
    return heater_nr


def _check_channel(channel_nr: int) -> int:
    if not 1 <= channel_nr <= 12:
        raise ValueError(f"channel_nr must be 1-12, got {channel_nr}")
    return channel_nr


class TemperatureController:
    """Connection to one Bluefors Temperature Controller.

    Args:
        host: IP address or host name of the Temperature Controller.
        timeout: Seconds to wait for each HTTP request.
        http_port: HTTP API port (default 5001).
        websocket_port: WebSocket API port (default 5002).

    Use it as a context manager to close the connection automatically::

        with TemperatureController("192.168.1.10") as tc:
            print(tc.latest_measurement(1))
    """

    def __init__(
        self,
        host: str,
        *,
        timeout: float = 10.0,
        http_port: int = HTTP_PORT,
        websocket_port: int = WEBSOCKET_PORT,
    ) -> None:
        self.host = _host_only(host)
        self.timeout = timeout
        self.http_port = http_port
        self.websocket_port = websocket_port
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"

    def __repr__(self) -> str:
        return f"TemperatureController({self.host!r})"

    def __enter__(self) -> TemperatureController:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the HTTP connection pool. Streams close themselves when they end."""
        self._session.close()

    # ------------------------------------------------------------------ transport

    def request(self, endpoint: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Call any request-response endpoint and return the decoded reply.

        Sends ``GET`` when ``payload`` is ``None`` and ``POST`` with a JSON body
        otherwise. Raises :class:`TCRequestError` if the Temperature Controller
        reports an error. Use this for endpoints that have no dedicated method.
        """
        endpoint = endpoint.strip("/")
        url = f"http://{self.host}:{self.http_port}/{endpoint}"
        try:
            if payload is None:
                response = self._session.get(url, timeout=self.timeout)
            else:
                response = self._session.post(url, json=payload, timeout=self.timeout)
        except requests.ConnectTimeout as exc:
            raise TCTimeoutError(
                f"Cannot connect to {self.host}:{self.http_port}: no answer within "
                f"{self.timeout} s. Check the address and that the controller is switched on."
            ) from exc
        except requests.Timeout as exc:
            raise TCTimeoutError(
                f"Connected to {self.host}:{self.http_port}, but it did not reply within "
                f"{self.timeout} s."
            ) from exc
        except requests.ConnectionError as exc:
            raise TCConnectionError(
                f"Cannot connect to {self.host}:{self.http_port}: "
                f"{_connection_problem(exc, self.http_port)}"
            ) from exc

        try:
            data = response.json()
        except ValueError:
            if response.status_code == 404:
                raise TCRequestError(endpoint, "unknown endpoint (HTTP 404)", payload) from None
            raise TCRequestError(
                endpoint, f"unexpected non-JSON reply (HTTP {response.status_code})", payload
            ) from None

        if not isinstance(data, dict):
            raise TCRequestError(endpoint, "unexpected reply format", payload)
        if data.get("status") == "ERROR" or response.status_code >= 400:
            raise TCRequestError.from_response(endpoint, payload, data)
        return data

    def _websocket(self, endpoint: str, timeout: float) -> websocket.WebSocket:
        url = f"ws://{self.host}:{self.websocket_port}/{endpoint}"
        try:
            return websocket.create_connection(url, timeout=timeout)
        except (OSError, websocket.WebSocketException) as exc:
            raise TCConnectionError(
                f"Cannot open WebSocket {url}: {_connection_problem(exc, self.websocket_port)}"
            ) from exc

    # ------------------------------------------------------------------ system

    def system(self) -> SystemInfo:
        """Serial number, label, software version and API version."""
        return SystemInfo.from_api(self.request("system"))

    def statemachine(self) -> StateMachine:
        """Measurement state: whether the controller is measuring, and which channel."""
        return StateMachine.from_api(self.request("statemachine"))

    # ------------------------------------------------------------------ channels

    def channels(self, include_internal: bool = False) -> list[Channel]:
        """Settings of channels 1-8, or 1-12 with ``include_internal=True``.

        Channels 9-12 are the built-in reference resistors, used for diagnostics.
        """
        items = [Channel.from_api(c) for c in self.request("channels").get("data", [])]
        return [c for c in items if include_internal or c.channel_nr in SAMPLE_CHANNELS]

    def channel(self, channel_nr: int) -> Channel:
        """Settings of one channel."""
        return Channel.from_api(self.request("channel", {"channel_nr": _check_channel(channel_nr)}))

    def update_channel(self, channel_nr: int, **settings: Any) -> Channel:
        """Change channel settings, for example ``active=True`` or ``calib_curve_nr=3``.

        Field names are those of ``/channel/update`` in the API technical reference.
        """
        payload = {"channel_nr": _check_channel(channel_nr), **settings}
        return Channel.from_api(self.request("channel/update", payload))

    def couple_heater(self, channel_nr: int, heater_nr: int) -> None:
        """Use channel ``channel_nr`` as the thermometer for heater ``heater_nr`` in PID mode.

        ``heater_nr=0`` removes the channel's heater coupling.
        """
        if heater_nr != 0:
            _check_heater(heater_nr)
        self.request(
            "channel/heater/update",
            {"channel_nr": _check_channel(channel_nr), "heater_nr": heater_nr},
        )

    # ------------------------------------------------------------------ measurements

    def latest_measurement(
        self, channel_nr: Optional[int] = None, lookback: timedelta = timedelta(hours=1)
    ) -> Measurement:
        """Most recent stored measurement, returned immediately.

        With ``channel_nr``, returns that channel's newest value from the
        controller's history (searching back ``lookback``); this has no
        ``status_flags``. Without it, returns the newest measurement of any
        channel, including flags. Use :meth:`next_measurement` to wait for a
        fresh reading with flags.

        Raises :class:`TCNoDataError` if the channel has no data in ``lookback``,
        for example because it is not active.
        """
        if channel_nr is None:
            return Measurement.from_api(self.request("channel/measurement/latest"))

        # Stop one day in the future so a computer clock that runs behind the
        # controller's clock does not hide the newest point.
        history = self.channel_history(
            channel_nr, start=lookback, stop=timedelta(days=-1), fields=_MEASUREMENT_FIELDS
        )
        if len(history) == 0:
            minutes = round(lookback.total_seconds() / 60)
            raise TCNoDataError(
                f"Channel {channel_nr}: no measurements in the last {minutes} minutes. Check "
                "that the channel is active and that the computer clock is correct."
            )
        newest = max(range(len(history)), key=lambda i: history["timestamp"][i])
        row = {name: values[newest] for name, values in history.columns.items()}
        return Measurement.from_api({"channel_nr": channel_nr, **row})

    def stream_measurements(
        self,
        channels: Optional[Iterable[int]] = None,
        *,
        duration: Optional[float] = None,
        idle_timeout: float = 120.0,
    ) -> Iterator[Measurement]:
        """Yield measurements as the controller publishes them.

        Args:
            channels: Only yield these channels (default: all).
            duration: Stop after this many seconds (default: run until the loop
                is broken).
            idle_timeout: Raise :class:`TCTimeoutError` if no measurement of any
                channel arrives for this many seconds.

        The controller measures one channel at a time, so each channel appears
        once per scan cycle.
        """
        wanted = None if channels is None else {_check_channel(c) for c in channels}
        deadline = None if duration is None else time.monotonic() + duration
        ws = self._websocket("channel/measurement/listen", timeout=idle_timeout)
        try:
            while deadline is None or time.monotonic() < deadline:
                if deadline is not None:
                    ws.settimeout(max(0.1, min(idle_timeout, deadline - time.monotonic())))
                try:
                    message = ws.recv()
                except websocket.WebSocketTimeoutException:
                    if deadline is not None and time.monotonic() >= deadline:
                        return
                    raise TCTimeoutError(
                        f"No measurements from {self.host} for {idle_timeout} s. Check that "
                        "the controller is measuring (see statemachine())."
                    ) from None
                except (OSError, websocket.WebSocketException) as exc:
                    raise TCConnectionError(
                        f"Measurement stream from {self.host} closed: {_root_cause(exc)}"
                    ) from exc
                data = json.loads(message)
                if "channel_nr" not in data:
                    continue
                measurement = Measurement.from_api(data)
                if wanted is None or measurement.channel_nr in wanted:
                    yield measurement
        finally:
            ws.close()

    def next_measurement(self, channel_nr: int, timeout: float = 300.0) -> Measurement:
        """Wait for the next live measurement of one channel, including status flags.

        This can take up to one full scan cycle. Raises :class:`TCTimeoutError`
        after ``timeout`` seconds, for example if the channel is not active.
        """
        _check_channel(channel_nr)
        for measurement in self.stream_measurements([channel_nr], duration=timeout):
            return measurement
        raise TCTimeoutError(
            f"No measurement of channel {channel_nr} within {timeout} s. "
            "Check that the channel is active."
        )

    def channel_history(
        self,
        channel_nr: int,
        start: TimeSpec,
        stop: Optional[TimeSpec] = None,
        fields: Sequence[str] = ("timestamp", "temperature", "resistance"),
    ) -> History:
        """Stored measurements of one channel between ``start`` and ``stop``.

        ``start`` and ``stop`` are datetimes (naive ones are local time), API
        time strings, or a ``timedelta`` meaning "this long ago". ``stop``
        defaults to now. Allowed fields: ``timestamp``, ``temperature``,
        ``resistance``, ``reactance``, ``rez``, ``imz``, ``magnitude``,
        ``angle``.
        """
        return self._history(
            "channel", "channel_nr", _check_channel(channel_nr), start, stop, fields
        )

    def heater_history(
        self,
        heater_nr: int,
        start: TimeSpec,
        stop: Optional[TimeSpec] = None,
        fields: Sequence[str] = ("timestamp", "power"),
    ) -> History:
        """Stored heater output (``power`` and/or ``current``) between ``start`` and ``stop``."""
        return self._history("heater", "heater_nr", _check_heater(heater_nr), start, stop, fields)

    def _history(
        self,
        kind: str,
        key: str,
        number: int,
        start: TimeSpec,
        stop: Optional[TimeSpec],
        fields: Sequence[str],
    ) -> History:
        now = datetime.now(timezone.utc)
        payload = {
            key: number,
            "start_time": _api_time(start, now),
            "stop_time": _api_time(stop, now),
            "fields": list(fields),
        }
        data = self.request(f"{kind}/historical-data", payload)
        if data.get("over_limit"):
            raise TCRequestError(
                f"{kind}/historical-data",
                "too many points requested (limit is 100 000); use a shorter time range",
                payload,
                data,
            )
        columns = data.get("measurements") or {}
        return History(columns={name: list(columns.get(name, [])) for name in columns}, raw=data)

    # ------------------------------------------------------------------ heaters

    def heaters(self) -> list[Heater]:
        """Settings of heaters 1-4."""
        return [Heater.from_api(h) for h in self.request("heaters").get("data", [])]

    def heater(self, heater_nr: int) -> Heater:
        """Settings of one heater."""
        return Heater.from_api(self.request("heater", {"heater_nr": _check_heater(heater_nr)}))

    def set_heater_power(self, heater_nr: int, power: float) -> Heater:
        """Switch a heater on in manual mode with a fixed output power in watts.

        The controller limits the output to the heater's ``max_power``.
        """
        payload = {
            "heater_nr": _check_heater(heater_nr),
            "active": True,
            "pid_mode": 0,
            "power": _check_number("power", power, 0.0, 1.0),
        }
        return Heater.from_api(self.request("heater/update", payload))

    def set_pid(
        self,
        heater_nr: int,
        setpoint: float,
        *,
        channel_nr: Optional[int] = None,
        max_power: Optional[float] = None,
        proportional: Optional[float] = None,
        integral: Optional[float] = None,
        derivative: Optional[float] = None,
    ) -> Heater:
        """Regulate to ``setpoint`` kelvin with the controller's PID loop.

        Args:
            heater_nr: Heater 1-4.
            setpoint: Target temperature in kelvin.
            channel_nr: Thermometer channel for the loop. If omitted, the
                channel already coupled to this heater is used.
            max_power: Hard power limit in watts. If omitted, the stored limit
                is kept.
            proportional, integral, derivative: PID gains. Gains that are
                omitted keep their stored values.

        PID gains depend on the cryostat and the temperature range; tune them
        for your system. Raises :class:`ValueError` if no thermometer channel
        is coupled to the heater. All arguments are checked before anything
        is sent, so a rejected call changes nothing on the controller.

        Warns with :class:`TCWarning` if the thermometer channel has measured
        no temperature in the last hour (no calibration curve, the resistance
        is outside the curve, or the channel is not active): the controller
        accepts the settings, but the loop has nothing to regulate on.
        """
        _check_heater(heater_nr)
        setpoint = _check_number("setpoint", setpoint, 0.0, 1000.0)
        if channel_nr is not None:
            _check_channel(channel_nr)
        if max_power is not None:
            max_power = _check_number("max_power", max_power, 0.0, 1.0)
        gains = {
            name: None if value is None else float(value)
            for name, value in (
                ("proportional", proportional),
                ("integral", integral),
                ("derivative", derivative),
            )
        }
        for name, value in gains.items():
            if value is not None and not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number, got {value}")

        if channel_nr is None:
            coupled = [
                c.channel_nr
                for c in self.channels(include_internal=True)
                if c.coupled_heater_nr == heater_nr
            ]
            if not coupled:
                raise ValueError(
                    f"Heater {heater_nr} has no thermometer channel coupled to it. Pass "
                    "channel_nr=... to choose the channel the PID loop should use."
                )
            self._warn_without_temperature(coupled[0], heater_nr)
        else:
            self._warn_without_temperature(channel_nr, heater_nr)
            self.couple_heater(channel_nr, heater_nr)

        payload: dict[str, Any] = {
            "heater_nr": heater_nr,
            "active": True,
            "pid_mode": 1,
            "setpoint": setpoint,
        }
        if max_power is not None:
            payload["max_power"] = max_power
        if any(v is not None for v in gains.values()):
            current = self.heater(heater_nr)
            payload["control_algorithm_settings"] = {
                name: value if value is not None else getattr(current, name)
                for name, value in gains.items()
            }
        return Heater.from_api(self.request("heater/update", payload))

    def _warn_without_temperature(self, channel_nr: int, heater_nr: int) -> None:
        """Warn if the PID thermometer channel has no temperature to regulate on.

        The check is advisory: if the history request itself fails, it is
        skipped so that it never stops the PID settings from being sent. A
        real connection problem then surfaces from the heater update.
        """
        try:
            measurement = self.latest_measurement(channel_nr)
        except TCNoDataError:
            reason = "has no measurements in the last hour; check that it is active"
        except TCError:
            return
        else:
            if measurement.temperature is not None:
                return
            reason = (
                "measures no temperature: it has no calibration curve, or the "
                "resistance is outside the curve"
            )
        warnings.warn(
            f"Heater {heater_nr}: thermometer channel {channel_nr} {reason}. "
            "The PID loop has nothing to regulate on.",
            TCWarning,
            stacklevel=3,
        )

    def heater_off(self, heater_nr: int) -> Heater:
        """Switch a heater off. Its other settings are kept."""
        payload = {"heater_nr": _check_heater(heater_nr), "active": False}
        return Heater.from_api(self.request("heater/update", payload))
