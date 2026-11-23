"""Download a channel's stored history to CSV, and optionally plot it.

Usage: python 05_historical_data.py 192.168.1.10 --channel 6 --hours 24 [--plot]
Plotting needs matplotlib: pip install matplotlib
"""

import argparse
import os
from datetime import timedelta

from bluefors_tc import TemperatureController

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--channel", type=int, default=1)
parser.add_argument("--hours", type=float, default=24.0, help="how far back to go")
parser.add_argument("--file", help="output file (default: channel<N>_history.csv)")
parser.add_argument("--plot", action="store_true", help="show a temperature plot")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

with TemperatureController(args.host) as tc:
    history = tc.channel_history(
        args.channel,
        start=timedelta(hours=args.hours),
        fields=["timestamp", "temperature", "resistance"],
    )

path = history.to_csv(args.file or f"channel{args.channel}_history.csv")
print(f"Saved {len(history)} points to {path}")

if args.plot and len(history):
    import matplotlib.pyplot as plt

    temperatures = [t if t is not None else float("nan") for t in history["temperature"]]
    times = [t.astimezone() for t in history.times]
    fig, ax = plt.subplots()
    ax.plot(times, temperatures, ".-")
    ax.set_yscale("log")
    ax.set_xlabel("Time")
    ax.set_ylabel("Temperature (K)")
    ax.set_title(f"Channel {args.channel}, last {args.hours:g} h")
    fig.autofmt_xdate()
    plt.show()
