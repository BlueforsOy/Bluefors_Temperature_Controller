"""QCoDeS instrument driver for the Bluefors Temperature Controller.

Install with ``pip install "bluefors-tc[qcodes]"``, then::

    from bluefors_tc.qcodes_driver import BlueforsTC

    tc = BlueforsTC("tc", "192.168.1.10")
    tc.ch1.temperature()          # latest stored value, in K
    tc.heater4.setpoint(0.050)    # PID to 50 mK on the coupled channel

Every parameter get is one request to the controller, so values are always
current. Setting ``power`` switches that heater to manual mode; setting
``setpoint`` switches it to PID mode.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, cast

from qcodes.instrument import (
    ChannelList,
    ChannelTuple,
    Instrument,
    InstrumentBaseKWArgs,
    InstrumentChannel,
)
from qcodes.parameters import Parameter
from qcodes.validators import Bool, Numbers

from .client import TemperatureController
from .models import HEATERS, SAMPLE_CHANNELS, Heater, Measurement

if TYPE_CHECKING:
    from typing_extensions import Unpack


def _or_nan(value: Optional[float]) -> float:
    return math.nan if value is None else value


class BlueforsTCChannel(InstrumentChannel):
    """One thermometer channel (1-8)."""

    def __init__(
        self,
        parent: BlueforsTC,
        name: str,
        channel_nr: int,
        **kwargs: Unpack[InstrumentBaseKWArgs],
    ) -> None:
        super().__init__(parent, name, **kwargs)
        self.channel_nr = channel_nr

        self.temperature: Parameter = self.add_parameter(
            "temperature",
            unit="K",
            label=f"Channel {channel_nr} temperature",
            get_cmd=lambda: _or_nan(self._latest().temperature),
            snapshot_get=False,  # a measured value: snapshots must not trigger a read
            docstring="Latest stored temperature; NaN if the channel has no calibration curve.",
        )
        """Latest stored temperature in K; NaN without a calibration curve."""

        self.resistance: Parameter = self.add_parameter(
            "resistance",
            unit="Ohm",
            label=f"Channel {channel_nr} resistance",
            get_cmd=lambda: _or_nan(self._latest().resistance),
            snapshot_get=False,
        )
        """Latest stored resistance in Ohm."""

        self.active: Parameter = self.add_parameter(
            "active",
            label=f"Channel {channel_nr} active",
            get_cmd=lambda: self._client.channel(channel_nr).active,
            set_cmd=lambda value: self._client.update_channel(channel_nr, active=bool(value)),
            vals=Bool(),
        )
        """Whether the controller measures this channel."""

    @property
    def _client(self) -> TemperatureController:
        return cast("BlueforsTC", self.root_instrument).client

    def _latest(self) -> Measurement:
        return self._client.latest_measurement(self.channel_nr)


class BlueforsTCHeater(InstrumentChannel):
    """One heater output (1-4)."""

    def __init__(
        self,
        parent: BlueforsTC,
        name: str,
        heater_nr: int,
        **kwargs: Unpack[InstrumentBaseKWArgs],
    ) -> None:
        super().__init__(parent, name, **kwargs)
        self.heater_nr = heater_nr

        self.active: Parameter = self.add_parameter(
            "active",
            label=f"Heater {heater_nr} on",
            get_cmd=lambda: self._heater().active,
            set_cmd=self._set_active,
            vals=Bool(),
        )
        """Whether the heater output is on."""

        self.mode: Parameter = self.add_parameter(
            "mode",
            label=f"Heater {heater_nr} mode",
            get_cmd=lambda: self._heater().mode,
            docstring='"manual" (fixed power) or "pid" (closed loop).',
        )
        """``"manual"`` (fixed power) or ``"pid"`` (closed loop)."""

        self.power: Parameter = self.add_parameter(
            "power",
            unit="W",
            label=f"Heater {heater_nr} manual power",
            get_cmd=lambda: self._heater().power,
            set_cmd=lambda watts: self._client.set_heater_power(heater_nr, watts),
            vals=Numbers(0, 1),
            docstring="Setting this switches the heater on in manual mode.",
        )
        """Manual-mode output power in W. Setting it switches the heater on in manual mode."""

        self.setpoint: Parameter = self.add_parameter(
            "setpoint",
            unit="K",
            label=f"Heater {heater_nr} PID setpoint",
            get_cmd=lambda: self._heater().setpoint,
            set_cmd=lambda kelvin: self._client.set_pid(heater_nr, kelvin),
            vals=Numbers(0, 1000),
            docstring="Setting this switches the heater on in PID mode, using the coupled channel.",
        )
        """PID setpoint in K. Setting it switches the heater on in PID mode."""

        self.max_power: Parameter = self.add_parameter(
            "max_power",
            unit="W",
            label=f"Heater {heater_nr} power limit",
            get_cmd=lambda: self._heater().max_power,
            set_cmd=lambda watts: self._client.request(
                "heater/update", {"heater_nr": heater_nr, "max_power": float(watts)}
            ),
            vals=Numbers(0, 1),
        )
        """Hard power limit in W."""

    @property
    def _client(self) -> TemperatureController:
        return cast("BlueforsTC", self.root_instrument).client

    def _heater(self) -> Heater:
        return self._client.heater(self.heater_nr)

    def _set_active(self, on: bool) -> None:
        if on:
            self._client.request("heater/update", {"heater_nr": self.heater_nr, "active": True})
        else:
            self._client.heater_off(self.heater_nr)


class BlueforsTC(Instrument):
    """Bluefors Temperature Controller.

    Args:
        name: QCoDeS instrument name.
        address: IP address or host name of the controller.
        timeout: HTTP timeout in seconds.
        print_connect_message: Print the controller's identity after connecting.
    """

    def __init__(
        self,
        name: str,
        address: str,
        *,
        timeout: float = 10.0,
        print_connect_message: bool = True,
        **kwargs: Unpack[InstrumentBaseKWArgs],
    ) -> None:
        super().__init__(name, **kwargs)
        self.client = TemperatureController(address, timeout=timeout)

        channels = ChannelList(self, "channels", BlueforsTCChannel)
        for nr in SAMPLE_CHANNELS:
            channel = BlueforsTCChannel(self, f"ch{nr}", nr)
            channels.append(channel)
            self.add_submodule(f"ch{nr}", channel)
        # add_submodule() returns None in QCoDeS 0.50 (the submodule in 0.61), so store it first.
        self.channels: ChannelTuple[BlueforsTCChannel] = channels.to_channel_tuple()
        self.add_submodule("channels", self.channels)
        """Thermometer channels 1-8, also available as ``ch1`` ... ``ch8``."""

        heaters = ChannelList(self, "heaters", BlueforsTCHeater)
        for nr in HEATERS:
            heater = BlueforsTCHeater(self, f"heater{nr}", nr)
            heaters.append(heater)
            self.add_submodule(f"heater{nr}", heater)
        # add_submodule() returns None in QCoDeS 0.50 (the submodule in 0.61), so store it first.
        self.heaters: ChannelTuple[BlueforsTCHeater] = heaters.to_channel_tuple()
        self.add_submodule("heaters", self.heaters)
        """Heater outputs 1-4, also available as ``heater1`` ... ``heater4``."""

        if print_connect_message:
            self.connect_message()

    def get_idn(self) -> dict[str, Optional[str]]:
        system = self.client.system()
        return {
            "vendor": "Bluefors",
            "model": "Temperature Controller",
            "serial": system.serial,
            "firmware": system.software_version,
        }

    def close(self) -> None:
        self.client.close()
        super().close()
