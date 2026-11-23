"""Print live measurements as the controller makes them, with status warnings.

Usage: python 03_stream_measurements.py 192.168.1.10 [--channels 1 2] [--duration 300]
Press Ctrl+C to stop.
"""

import argparse
import os

from bluefors_tc import TemperatureController

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--channels", type=int, nargs="+", help="channels to show (default: all)")
parser.add_argument("--duration", type=float, help="stop after this many seconds")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

with TemperatureController(args.host) as tc:
    try:
        for m in tc.stream_measurements(args.channels, duration=args.duration):
            when = m.timestamp.astimezone().strftime("%I:%M:%S %p")
            # Temperature, or resistance when there is no temperature (as the UI shows)
            print(f"{when}  channel {m.channel_nr:>2}  {m.display_value:>14}", flush=True)
            for flag in m.flags:
                print(f"           {flag.severity}: {flag.name}. {flag.description}")
    except KeyboardInterrupt:
        print("Stopped.")
