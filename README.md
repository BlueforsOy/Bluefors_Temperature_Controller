# bluefors-tc

Python client, command-line tool and QCoDeS driver for the **Bluefors Temperature Controller**.

- Read temperatures and resistances, live or from the controller's history.
- Set heater power, or regulate a temperature with the controller's PID loop.
- Save data to CSV, or use the controller as a QCoDeS instrument.
- Clear error messages: rejected requests, timeouts and connection problems raise specific exceptions.

```python
from bluefors_tc import TemperatureController

with TemperatureController("192.168.1.10") as tc:
    print(tc.latest_measurement(1))
    # Channel 1: 12.345 mK, R = 18.300 kOhm
```

## Requirements

- Bluefors Temperature Controller (TC 1.0 or TC 1.1) with software 2.x. Tested with software 2.0.1 (API version 2) on both models.
- Python 3.10 or newer, on Windows, macOS or Linux.
- A network connection to the controller. The client uses TCP port 5001 (HTTP) and port 5002 (WebSocket); MQTT examples also use port 1883.

## Installation

From a checkout of this repository:

```bash
pip install .
```

Optional extras:

| Extra | Adds | Install |
|---|---|---|
| `qcodes` | QCoDeS instrument driver | `pip install ".[qcodes]"` |
| `mqtt` | MQTT example dependencies | `pip install ".[mqtt]"` |
| `examples` | Plotting in the examples | `pip install ".[examples]"` |

## Quick start

### Check the connection from the command line

```bash
bluefors-tc --host 192.168.1.10 info
bluefors-tc --host 192.168.1.10 read
bluefors-tc --host 192.168.1.10 watch 1 2 --duration 300
```

Set `BLUEFORS_TC_HOST=192.168.1.10` to leave out `--host`. The command-line tool only reads; it never changes settings.

### Read temperatures

```python
from bluefors_tc import TemperatureController

with TemperatureController("192.168.1.10") as tc:
    for channel in tc.channels():
        if channel.active:
            m = tc.latest_measurement(channel.channel_nr)
            print(channel.name, m.display_value)
```

The controller measures one channel at a time and cycles through the active channels. There are two ways to read a channel:

| Method | Returns | Speed | Status flags |
|---|---|---|---|
| `latest_measurement(ch)` | The newest stored value | Immediate | No |
| `next_measurement(ch)` | The next fresh measurement | Up to one scan cycle | Yes |

`latest_measurement()` with no channel returns the newest measurement of any channel, with status flags.

`m.display_value` is what the controller's screen shows: the temperature, or the resistance when there is no temperature, for example because the channel has no calibration curve. `format_temperature()`, `format_resistance()` and `format_power()` use the same five-significant-digit format as the screen.

### Stream live measurements

```python
for m in tc.stream_measurements(channels=[1, 2], duration=600):
    print(m.timestamp, m.channel_nr, m.temperature)
    if m.has_error:
        print("  ", m.flags)
```

### Historical data

```python
from datetime import timedelta

history = tc.channel_history(1, start=timedelta(hours=24))
history.to_csv("channel1.csv")
```

`start` and `stop` accept a `datetime` (naive values are the computer's local time), a `timedelta` meaning "this long ago", or an API time string such as `"2026-10-12T08:00:00Z"`. The controller returns at most 100 000 points per request; split longer ranges.

### Heaters

> **Caution:** heater commands change the state of your cryostat. Check the heater's power limit (`tc.heater(n).max_power`) before you start, and test new settings on a warm system first.

```python
tc.set_heater_power(4, 100e-6)  # manual mode, 100 µW
tc.set_pid(4, setpoint=0.050)  # PID to 50 mK on the channel coupled to heater 4
tc.set_pid(
    4,
    0.100,
    channel_nr=1,  # choose the thermometer channel and gains
    proportional=0.05,
    integral=200,
    derivative=0,
    max_power=1e-3,
)
tc.heater_off(4)
```

`set_pid()` changes only what you pass: omitted gains and the power limit keep their stored values. PID gains depend on the cryostat and the temperature range, so tune them for your system. [`examples/10_zone_pid.py`](examples/10_zone_pid.py) shows how to use different gains for different temperature ranges.

### QCoDeS

```python
from bluefors_tc.qcodes_driver import BlueforsTC

tc = BlueforsTC("tc", "192.168.1.10")
tc.ch1.temperature()  # K
tc.heater4.setpoint(0.050)  # PID mode
tc.heater4.power()  # W
```

Each channel (`ch1`…`ch8`, or `tc.channels`) has `temperature`, `resistance` and `active`. Each heater (`heater1`…`heater4`, or `tc.heaters`) has `active`, `mode`, `power`, `setpoint` and `max_power`. A temperature reads as NaN when the channel has no calibration curve; read `resistance` instead.

Record them like any other QCoDeS parameter, with `Measurement` or `dond`. [`examples/08_qcodes.py`](examples/08_qcodes.py) records every active channel into a QCoDeS database. Snapshots don't read `temperature` or `resistance`, so a station snapshot stays fast and works when channels are inactive. The driver works with QCoDeS 0.50 and newer.

## Channels 1–8 and 9–12

Channels 1–8 are the sample inputs. Channels 9–12 are built-in reference resistors (10 kΩ, 1 kΩ, 100 Ω and 10 Ω) used for diagnostics. `channels()` returns channels 1–8; use `channels(include_internal=True)` for all twelve.

## Errors

All exceptions derive from `bluefors_tc.TCError`:

| Exception | Meaning |
|---|---|
| `TCConnectionError` | The controller cannot be reached |
| `TCTimeoutError` | No answer, or no measurement, in time |
| `TCRequestError` | The controller rejected the request; `.message` has its reason |
| `TCNoDataError` | No data for the request, for example an inactive channel |

Invalid arguments, such as heater 5 or a negative power, raise `ValueError` before anything is sent.

`set_pid()` warns with `bluefors_tc.TCWarning` when the thermometer channel has measured no temperature in the last hour (no calibration curve, a resistance outside the curve, or an inactive channel). The controller accepts the settings, but the loop has nothing to regulate on.

## Examples

The [`examples`](examples) folder has short, runnable scripts. Each takes the controller address as its first argument or from `BLUEFORS_TC_HOST`.

| Script | What it does |
|---|---|
| `01_connect.py` | Show the controller's identity and measuring state |
| `02_read_temperatures.py` | Print the latest value of every active channel |
| `03_stream_measurements.py` | Print live measurements with status warnings |
| `04_log_to_csv.py` | Record live measurements to a CSV file |
| `05_historical_data.py` | Download history to CSV, and plot it |
| `06_heater_manual_power.py` | Set a fixed heater power (asks for confirmation) |
| `07_heater_pid.py` | Regulate to a setpoint and follow the temperature (asks for confirmation) |
| `08_qcodes.py` | Record every active channel into a QCoDeS dataset (read-only) |
| `09_mqtt_subscribe.py` | Receive measurements over MQTT without this package |
| `10_zone_pid.py` | Zone PID: pick gains and a power limit from the setpoint, and step through setpoints (`--dry-run` shows the plan) |

## Other endpoints

Every API endpoint is available through `tc.request(endpoint, payload)`. It sends `GET` without a payload and `POST` with one, and returns the decoded reply:

```python
tc.request("calibration-curves")
tc.request("channel/update", {"channel_nr": 3, "active": True})
```

Endpoints and fields are described in the *Bluefors Temperature Controller API Technical Reference*.

## Troubleshooting

| Symptom | What to check |
|---|---|
| `TCConnectionError` | The address; that the computer and the controller are on the same network; that a firewall allows ports 5001 and 5002 |
| A host name does not resolve | Use the IP address shown on the controller's network settings screen |
| `TCNoDataError` for a channel | The channel is not active, or the computer clock is far from the controller's clock |
| `next_measurement()` is slow | Normal: it waits for the channel's turn in the scan. Use `latest_measurement()` instead |
| `temperature` is `None` | The channel has no calibration curve (status flag 519) or the reading is outside the curve; see `m.flags`. `m.display_value` shows the resistance instead |

## Development

The project uses [uv](https://docs.astral.sh/uv/). Tool versions are pinned in `uv.lock`; after changing dependencies in `pyproject.toml`, run `uv lock` and commit both files.

```bash
uv sync --all-extras        # create .venv with the package, all extras and the dev tools
uv run pytest
uv run ruff check           # lint, including McCabe complexity (max 10)
uv run ruff format --check
uv run mypy                 # strict type check of src/
uv run deptry .             # imports match the declared dependencies
```

Without uv: `pip install -e ".[qcodes]"` and `pip install --group dev` (pip 25.1 or newer).

The tests run against a built-in fake controller. To also test a real controller:

```bash
uv run pytest -m live --tc-host 192.168.1.10                     # read-only
uv run pytest -m live --tc-host 192.168.1.10 --tc-allow-writes   # also heater 4, restored afterwards
```

Run write tests only on a controller that is not regulating a cryostat.

## Support

Contact Bluefors support at [support@bluefors.com](mailto:support@bluefors.com) or [bluefors.com/support](https://bluefors.com/support).

## License

MIT; see [LICENSE](LICENSE).
