"""Connect to a Bluefors Temperature Controller and show what it is doing.

Usage: python 01_connect.py 192.168.1.10
"""

import argparse
import os

from bluefors_tc import TemperatureController

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

with TemperatureController(args.host) as tc:
    system = tc.system()
    print(f"Connected to {tc.host}")
    print(f"  Serial number:    {system.serial}")
    print(f"  Software version: {system.software_version}")
    print(f"  API version:      {system.api_version}")

    state = tc.statemachine()
    if state.measuring:
        print(f"  Measuring channel {state.channel_nr}")
    else:
        print("  Not measuring")

    active = [c.channel_nr for c in tc.channels() if c.active]
    print(f"  Active channels:  {active}")
