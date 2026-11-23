"""Regulate a temperature with the controller's PID loop and follow it.

Usage:
    python 07_heater_pid.py 192.168.1.10 --heater 4 --setpoint-mk 50 [--channel 6]

The PID loop runs on the controller, not in this script: stopping the script
leaves the heater regulating. Switch it off with 06_heater_manual_power.py --off.

PID gains and the power limit are kept as stored on the controller unless you
pass them. Good values depend on your cryostat; tune them for your system.
"""

import argparse
import os
import time

from bluefors_tc import TCTimeoutError, TemperatureController, format_power, format_temperature

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--heater", type=int, required=True, help="heater number, 1-4")
parser.add_argument("--setpoint-mk", type=float, required=True, help="target in millikelvin")
parser.add_argument("--channel", type=int, help="thermometer channel (default: coupled one)")
parser.add_argument("--max-power-uw", type=float, help="power limit in microwatts")
parser.add_argument("--p", type=float, help="proportional gain")
parser.add_argument("--i", type=float, help="integral gain")
parser.add_argument("--d", type=float, help="derivative gain")
parser.add_argument("--follow-minutes", type=float, default=10, help="how long to print")
parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

setpoint = args.setpoint_mk / 1000

with TemperatureController(args.host) as tc:
    channel_nr = args.channel
    if channel_nr is None:
        coupled = [c for c in tc.channels() if c.coupled_heater_nr == args.heater]
        if not coupled:
            raise SystemExit(f"No channel is coupled to heater {args.heater}; use --channel.")
        channel_nr = coupled[0].channel_nr

    heater = tc.heater(args.heater)
    # What set_pid() will apply: the values passed, or the stored ones it keeps.
    limit = heater.max_power if args.max_power_uw is None else args.max_power_uw * 1e-6
    gains = [
        ("P", heater.proportional, args.p),
        ("I", heater.integral, args.i),
        ("D", heater.derivative, args.d),
    ]

    def show(name, kept, new):
        value = kept if new is None else new
        text = "?" if value is None else f"{value:g}"
        return f"{name}={text}" + (" (kept)" if new is None else "")

    state = "on" if heater.active else "off"
    print(f"{heater.name} now: {state}, {heater.mode} mode, limit {format_power(heater.max_power)}")
    print(f"Will regulate channel {channel_nr} to {format_temperature(setpoint)} with:")
    kept = " (kept)" if args.max_power_uw is None else ""
    print(f"  power limit {format_power(limit)}{kept}")
    print("  " + ", ".join(show(*g) for g in gains))
    question = "Continue? [y/N] "
    if not args.yes and input(question).strip().lower() != "y":
        raise SystemExit("Nothing changed.")

    tc.set_pid(
        args.heater,
        setpoint,
        channel_nr=args.channel,
        max_power=None if args.max_power_uw is None else args.max_power_uw * 1e-6,
        proportional=args.p,
        integral=args.i,
        derivative=args.d,
    )
    print(
        f"PID on. Following channel {channel_nr} for {args.follow_minutes:g} min "
        "(Ctrl+C stops following; the heater keeps regulating)."
    )

    end = time.monotonic() + args.follow_minutes * 60
    try:
        while time.monotonic() < end:
            try:
                m = tc.next_measurement(channel_nr)
            except TCTimeoutError:
                continue
            off = ""
            if m.temperature is not None:
                diff = m.temperature - setpoint
                sign = "+" if diff >= 0 else "-"
                off = f"{sign}{format_temperature(abs(diff))} from setpoint"
            print(f"{time.strftime('%I:%M:%S %p')}  {m.display_value}  {off}")
    except KeyboardInterrupt:
        pass
    print("Stopped following. The heater is still regulating.")
