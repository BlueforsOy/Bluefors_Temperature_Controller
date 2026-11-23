"""Zone PID: choose PID gains and a power limit from the setpoint, then regulate.

Usage:
    python 10_zone_pid.py --dry-run --setpoints-mk 20 50 100 300 1500
    python 10_zone_pid.py 192.168.1.10 --heater 4 --setpoints-mk 20 50 100 --hold-minutes 30

One set of PID gains rarely works over the whole temperature range. This
script looks up the gains for each setpoint in the ZONES table, limits the
heater power with a power curve, and steps through the setpoints, holding
each one for --hold-minutes. --dry-run prints the plan without connecting.

The PID loop runs on the controller, not in this script: when the script ends
or is stopped, the heater keeps regulating at the last setpoint (unless you
pass --off-at-end).

The values below are starting points for the mixing chamber of an empty
Bluefors LD system. Tune ZONES and the power curve for your system: run a
power sweep (heater power against stable temperature) and fit the curve.
"""

import argparse
import math
import os
import time
from typing import NamedTuple

from bluefors_tc import TCTimeoutError, TemperatureController, format_power, format_temperature


class Zone(NamedTuple):
    upper_k: float  # the zone covers setpoints up to and including this temperature
    proportional: float
    integral: float
    derivative: float


# Edit these for your system. Zones are checked in order; the first zone whose
# upper limit is at or above the setpoint is used.
ZONES = [
    Zone(0.080, proportional=0.01, integral=500, derivative=0.0),  # up to 80 mK
    Zone(0.500, proportional=0.03, integral=500, derivative=0.05),  # 80-500 mK
    Zone(1.0, proportional=0.05, integral=200, derivative=0.05),  # 0.5-1 K
    Zone(2.0, proportional=0.05, integral=200, derivative=0.05),  # 1-2 K
    Zone(math.inf, proportional=0.05, integral=200, derivative=0.05),  # above 2 K
]

# Power limit for a setpoint T (in K): MARGIN * A * T**B, capped at CAP watts.
# A * T**B is the heater power that holds the flange at T.
POWER_CURVE_A = 2.13709e-5  # W / K**B
POWER_CURVE_B = 2.7726
POWER_MARGIN = 1.2
POWER_CAP_W = 3e-3


def zone_for(setpoint_k: float) -> Zone:
    for zone in ZONES:
        if setpoint_k <= zone.upper_k:
            return zone
    raise ValueError(f"No zone covers {setpoint_k} K; check the ZONES table.")


def power_limit(setpoint_k: float) -> float:
    return min(POWER_MARGIN * POWER_CURVE_A * setpoint_k**POWER_CURVE_B, POWER_CAP_W)


def _short(kelvin: float) -> str:
    return f"{kelvin * 1000:g} mK" if kelvin < 1 else f"{kelvin:g} K"


def zone_range(zone: Zone) -> str:
    """For example "up to 80 mK", "80 mK to 500 mK" or "above 2 K"."""
    index = ZONES.index(zone)
    if index == 0:
        return f"up to {_short(zone.upper_k)}"
    lower = _short(ZONES[index - 1].upper_k)
    return f"above {lower}" if math.isinf(zone.upper_k) else f"{lower} to {_short(zone.upper_k)}"


parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--heater", type=int, help="heater number, 1-4")
parser.add_argument("--setpoints-mk", type=float, nargs="+", required=True, help="in mK")
parser.add_argument("--channel", type=int, help="thermometer channel (default: coupled one)")
parser.add_argument("--hold-minutes", type=float, default=30, help="time at each setpoint")
parser.add_argument("--max-power-uw", type=float, help="fixed power limit instead of the curve")
parser.add_argument("--off-at-end", action="store_true", help="switch the heater off at the end")
parser.add_argument("--dry-run", action="store_true", help="print the plan and exit")
parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
args = parser.parse_args()

plan = []
for setpoint_mk in args.setpoints_mk:
    setpoint = setpoint_mk / 1000
    if setpoint < 0:
        parser.error(f"setpoint {setpoint_mk} mK is negative")
    limit = power_limit(setpoint) if args.max_power_uw is None else args.max_power_uw * 1e-6
    plan.append((setpoint, zone_for(setpoint), limit))

print(f"{'Setpoint':>12}  {'Zone':<22} {'P':>6} {'I':>6} {'D':>6}  {'Power limit':>12}")
for setpoint, zone, limit in plan:
    print(
        f"{format_temperature(setpoint):>12}  {zone_range(zone):<22} {zone.proportional:>6g} "
        f"{zone.integral:>6g} {zone.derivative:>6g}  {format_power(limit):>12}"
    )
if args.dry_run:
    raise SystemExit

if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")
if args.heater is None:
    parser.error("--heater is required unless --dry-run is given")

with TemperatureController(args.host) as tc:
    channel_nr = args.channel
    if channel_nr is None:
        coupled = [c for c in tc.channels() if c.coupled_heater_nr == args.heater]
        if not coupled:
            raise SystemExit(f"No channel is coupled to heater {args.heater}; use --channel.")
        channel_nr = coupled[0].channel_nr

    question = (
        f"\nAbout to regulate channel {channel_nr} with heater {args.heater} through "
        f"{len(plan)} setpoint(s), {args.hold_minutes:g} min each. Continue? [y/N] "
    )
    if not args.yes and input(question).strip().lower() != "y":
        raise SystemExit("Nothing changed.")

    try:
        for step, (setpoint, zone, limit) in enumerate(plan, start=1):
            tc.set_pid(
                args.heater,
                setpoint,
                channel_nr=args.channel,
                max_power=limit,
                proportional=zone.proportional,
                integral=zone.integral,
                derivative=zone.derivative,
            )
            target = format_temperature(setpoint)
            print(f"\nStep {step}/{len(plan)}: {target} ({zone_range(zone)})")
            print(
                f"  P={zone.proportional:g} I={zone.integral:g} D={zone.derivative:g}, "
                f"power limit {format_power(limit)}"
            )

            end = time.monotonic() + args.hold_minutes * 60
            while time.monotonic() < end:
                try:
                    m = tc.next_measurement(channel_nr, timeout=max(1.0, end - time.monotonic()))
                except TCTimeoutError:
                    continue
                off = ""
                if m.temperature is not None:
                    diff = m.temperature - setpoint
                    sign = "+" if diff >= 0 else "-"
                    off = f"{sign}{format_temperature(abs(diff))} from setpoint"
                print(f"  {time.strftime('%I:%M:%S %p')}  {m.display_value}  {off}")
    except KeyboardInterrupt:
        print("\nStopped.")

    if args.off_at_end:
        tc.heater_off(args.heater)
        print(f"Heater {args.heater} switched off.")
    else:
        heater = tc.heater(args.heater)
        print(f"Heater {args.heater} keeps regulating at {format_temperature(heater.setpoint)}.")
