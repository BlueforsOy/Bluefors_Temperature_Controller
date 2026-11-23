"""Set a fixed heater power (manual mode), or switch a heater off.

Usage:
    python 06_heater_manual_power.py 192.168.1.10 --heater 4 --power-uw 100
    python 06_heater_manual_power.py 192.168.1.10 --heater 4 --off

This changes the state of your cryostat. The script shows the current heater
settings and asks for confirmation before it changes anything.
"""

import argparse
import os

from bluefors_tc import TemperatureController, format_power, format_temperature

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--heater", type=int, required=True, help="heater number, 1-4")
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--power-uw", type=float, help="output power in microwatts")
group.add_argument("--off", action="store_true", help="switch the heater off")
parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")


def show(heater):
    state = "on" if heater.active else "off"
    print(f"  {heater.name}: {state}, {heater.mode} mode")
    power, limit = format_power(heater.power), format_power(heater.max_power)
    print(f"  Manual power: {power}, power limit: {limit}")
    if heater.pid_mode:
        print(f"  PID setpoint: {format_temperature(heater.setpoint)}")


with TemperatureController(args.host) as tc:
    print("Current settings:")
    show(tc.heater(args.heater))

    if args.off:
        action = f"switch heater {args.heater} off"
    else:
        power = args.power_uw * 1e-6
        action = f"set heater {args.heater} to {args.power_uw:g} µW in manual mode"
    if not args.yes and input(f"\nAbout to {action}. Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("Nothing changed.")

    heater = tc.heater_off(args.heater) if args.off else tc.set_heater_power(args.heater, power)
    print("\nNew settings:")
    show(heater)
