"""Print the latest temperature of every active channel.

Usage: python 02_read_temperatures.py 192.168.1.10
"""

import argparse
import os

from bluefors_tc import TCNoDataError, TemperatureController, format_resistance

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

with TemperatureController(args.host) as tc:
    print(f"{'Channel':<20} {'Value':>14} {'Resistance':>14}  Measured")
    for channel in tc.channels():
        if not channel.active:
            continue
        try:
            m = tc.latest_measurement(channel.channel_nr)
        except TCNoDataError:
            print(f"{channel.name:<20} {'no data':>14}")
            continue
        # display_value is the temperature, or the resistance when there is no
        # temperature (for example no calibration curve), as on the controller's screen.
        when = m.timestamp.astimezone().strftime("%I:%M:%S %p")
        resistance = format_resistance(m.resistance) if m.temperature is not None else ""
        print(f"{channel.name:<20} {m.display_value:>14} {resistance:>14}  {when}")
