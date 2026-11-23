"""Record the Temperature Controller's channels into a QCoDeS dataset.

Usage: python 08_qcodes.py 192.168.1.10 [--minutes 5] [--interval 10] [--db tc_example.db]
Needs QCoDeS: pip install "bluefors-tc[qcodes]"

The script only reads: it records the temperature and resistance of every
active channel against elapsed time, then prints where the dataset is saved.
Open it later with qcodes.dataset.load_by_id(), or plot it with plot_dataset().
"""

import argparse
import math
import os
import time

from qcodes.dataset import (
    Measurement,
    initialise_or_create_database_at,
    load_or_create_experiment,
)
from qcodes.parameters import ElapsedTimeParameter
from qcodes.station import Station

from bluefors_tc import format_resistance, format_temperature
from bluefors_tc.qcodes_driver import BlueforsTC

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
parser.add_argument("--minutes", type=float, default=5, help="how long to record")
parser.add_argument("--interval", type=float, default=10, help="seconds between points")
parser.add_argument("--db", default="tc_example.db", help="QCoDeS database file")
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")

tc = BlueforsTC("bftc", args.host)
station = Station(tc)  # the station snapshot is saved with the dataset

initialise_or_create_database_at(args.db)
experiment = load_or_create_experiment("bluefors_tc_example", sample_name="cryostat")

try:
    channels = [channel for channel in tc.channels if channel.active()]
    if not channels:
        raise SystemExit("No active channels to record.")

    for channel in channels:
        temperature = channel.temperature()
        if math.isnan(temperature):  # no calibration curve: show resistance, as the UI does
            print(f"{channel.short_name}: {format_resistance(channel.resistance())}")
        else:
            print(f"{channel.short_name}: {format_temperature(temperature)}")

    elapsed = ElapsedTimeParameter("elapsed_time")
    meas = Measurement(exp=experiment, station=station, name="tc_channels")
    meas.register_parameter(elapsed)
    for channel in channels:
        meas.register_parameter(channel.temperature, setpoints=(elapsed,))
        meas.register_parameter(channel.resistance, setpoints=(elapsed,))

    print(
        f"\nRecording {len(channels)} channel(s) every {args.interval:g} s "
        f"for {args.minutes:g} min. Press Ctrl+C to stop early."
    )
    points = 0
    with meas.run() as datasaver:
        elapsed.reset_clock()
        try:
            while elapsed() < args.minutes * 60:
                now = elapsed()
                results = [(elapsed, now)]
                for channel in channels:
                    results.append((channel.temperature, channel.temperature()))
                    results.append((channel.resistance, channel.resistance()))
                datasaver.add_result(*results)
                points += 1
                time.sleep(max(0.0, args.interval - (elapsed() - now)))
        except KeyboardInterrupt:
            print("Stopped.")
        dataset = datasaver.dataset

    print(f"Saved dataset {dataset.run_id} ({points} points) to {args.db}")

    # The controller measures one channel at a time, so a channel's value only
    # changes once per scan cycle; points in between repeat the latest value.
    #
    # Heaters are parameters too. For example, step heater 4's PID setpoint and
    # record channel 6 (this changes the cryostat's temperature):
    #   from qcodes.dataset import LinSweep, dond
    #   dond(LinSweep(tc.heater4.setpoint, 0.02, 0.1, 9, delay=600), tc.ch6.temperature)
finally:
    tc.close()
