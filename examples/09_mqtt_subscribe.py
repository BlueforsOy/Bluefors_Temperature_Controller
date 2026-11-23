"""Receive live measurements over MQTT, without the bluefors_tc package.

The controller runs its own MQTT broker on port 1883. This is useful for
dashboards and data pipelines that already speak MQTT.

Usage: python 09_mqtt_subscribe.py 192.168.1.10
Needs paho-mqtt: pip install paho-mqtt
"""

import argparse
import json
import os

import paho.mqtt.subscribe as subscribe

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("host", nargs="?", default=os.environ.get("BLUEFORS_TC_HOST"))
args = parser.parse_args()
if not args.host:
    parser.error("give the controller address, or set BLUEFORS_TC_HOST")


def on_message(client, userdata, message):
    data = json.loads(message.payload)
    # Show the temperature, or the resistance when there is no temperature
    # (for example no calibration curve), as the controller's screen does.
    if data["temperature"] is not None:
        value = f"T = {data['temperature']:.5g} K"
    elif data["resistance"] is not None:
        value = f"R = {data['resistance']:.6g} Ohm"  # .6g: no exponent below 1 MOhm
    else:
        value = "no value"
    print(f"channel {data['channel_nr']:>2}: {value}, flags = {data['status_flags']}", flush=True)


# Subscriptions use the bare ".../listen" topic; nothing needs to be published first.
print("Waiting for measurements, press Ctrl+C to stop...")
try:
    subscribe.callback(on_message, "channel/measurement/listen", hostname=args.host, port=1883)
except KeyboardInterrupt:
    pass
