"""``bluefors-tc`` command-line tool: quick, read-only checks of a Temperature Controller."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional

from . import __version__
from .client import TemperatureController
from .exceptions import TCError
from .models import SAMPLE_CHANNELS, format_power, format_temperature


def _info(tc: TemperatureController, args: argparse.Namespace) -> None:
    system = tc.system()
    sm = tc.statemachine()
    print(f"Host:             {tc.host}")
    print(f"Serial number:    {system.serial}")
    print(f"Label:            {system.label}")
    print(f"Software version: {system.software_version}")
    print(f"API version:      {system.api_version}")
    measuring = f"yes (channel {sm.channel_nr})" if sm.measuring else "no"
    print(f"Measuring:        {measuring}")


def _channels(tc: TemperatureController, args: argparse.Namespace) -> None:
    print(f"{'Ch':>3}  {'Active':<6}  {'Curve':>5}  {'Heater':>6}  Name")
    for c in tc.channels(include_internal=args.all):
        heater = str(c.coupled_heater_nr) if c.coupled_heater_nr else "-"
        curve = "-" if c.calib_curve_nr is None else str(c.calib_curve_nr)
        active = "yes" if c.active else "no"
        print(f"{c.channel_nr:>3}  {active:<6}  {curve:>5}  {heater:>6}  {c.name}")


def _heaters(tc: TemperatureController, args: argparse.Namespace) -> None:
    print(
        f"{'Htr':>3}  {'Active':<6}  {'Mode':<6}  {'Manual power':>12}  {'Power limit':>12}  "
        f"{'Setpoint':>12}  Name"
    )
    for h in tc.heaters():
        # Only the setting of the current mode: in PID mode the stored manual
        # power is not the output. The HTTP API has no reading of the actual output.
        setpoint = format_temperature(h.setpoint) if h.pid_mode else "-"
        power = "-" if h.pid_mode else format_power(h.power)
        limit = format_power(h.max_power)
        print(
            f"{h.heater_nr:>3}  {'yes' if h.active else 'no':<6}  {h.mode:<6}  "
            f"{power:>12}  {limit:>12}  {setpoint:>12}  {h.name}"
        )


def _active_channels(tc: TemperatureController, requested: list[int]) -> list[int]:
    if requested:
        return requested
    return [c.channel_nr for c in tc.channels() if c.active]


def _read(tc: TemperatureController, args: argparse.Namespace) -> None:
    for channel_nr in _active_channels(tc, args.channel):
        try:
            m = tc.latest_measurement(channel_nr)
        except TCError as exc:
            print(exc)
            continue
        when = m.timestamp.astimezone().strftime("%Y-%m-%d %I:%M:%S %p") if m.timestamp else "?"
        print(f"{m}  (measured {when})")


def _watch(tc: TemperatureController, args: argparse.Namespace) -> None:
    channels = args.channel or None
    print("Waiting for measurements, press Ctrl+C to stop...", file=sys.stderr)
    try:
        for m in tc.stream_measurements(channels, duration=args.duration):
            when = m.timestamp.astimezone().strftime("%I:%M:%S %p") if m.timestamp else "?"
            print(f"{when}  {m}", flush=True)
    except KeyboardInterrupt:
        pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bluefors-tc",
        description="Read-only checks of a Bluefors Temperature Controller.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("BLUEFORS_TC_HOST"),
        help="IP address or host name (default: $BLUEFORS_TC_HOST)",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout in seconds")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="serial number, software version, measuring state").set_defaults(
        func=_info
    )
    p = sub.add_parser("channels", help="channel settings")
    p.add_argument("--all", action="store_true", help="include internal channels 9-12")
    p.set_defaults(func=_channels)
    sub.add_parser("heaters", help="heater settings").set_defaults(func=_heaters)

    channel_help = f"channel numbers ({SAMPLE_CHANNELS[0]}-{SAMPLE_CHANNELS[-1]}; default: active)"
    p = sub.add_parser("read", help="latest measurement of each channel")
    p.add_argument("channel", nargs="*", type=int, help=channel_help)
    p.set_defaults(func=_read)
    p = sub.add_parser("watch", help="print live measurements as they arrive")
    p.add_argument("channel", nargs="*", type=int, help="channel numbers (default: all)")
    p.add_argument("--duration", type=float, help="stop after this many seconds")
    p.set_defaults(func=_watch)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.host:
        print("error: give --host or set BLUEFORS_TC_HOST", file=sys.stderr)
        return 2
    try:
        with TemperatureController(args.host, timeout=args.timeout) as tc:
            args.func(tc, args)
    except (TCError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
