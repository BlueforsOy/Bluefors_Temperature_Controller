"""Record live measurements to a CSV file.

Usage: python 04_log_to_csv.py 192.168.1.10 --hours 12 --file cooldown.csv
Press Ctrl+C to stop early; rows already written are kept.
"""

import argparse
import csv
import os

from bluefors_tc import TemperatureController

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--channels", type=int, nargs="+", help="channels to record (default: all)")
parser.add_argument("--hours", type=float, default=1.0, help="how long to record")
parser.add_argument("--file", default="measurements.csv", help="output file")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

columns = ["utc_time", "unix_time", "channel", "temperature_K", "resistance_Ohm", "status_flags"]

with TemperatureController(args.host) as tc, open(args.file, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(columns)
    print(f"Recording to {args.file} for {args.hours} h. Press Ctrl+C to stop.")
    rows = 0
    try:
        for m in tc.stream_measurements(args.channels, duration=args.hours * 3600):
            writer.writerow(
                [
                    m.timestamp.isoformat(),
                    m.timestamp.timestamp(),
                    m.channel_nr,
                    "" if m.temperature is None else m.temperature,
                    "" if m.resistance is None else m.resistance,
                    " ".join(str(code) for code in m.status_flags or ()),
                ]
            )
            f.flush()  # keep the file usable if the script is stopped
            rows += 1
    except KeyboardInterrupt:
        pass
    print(f"Wrote {rows} rows.")
