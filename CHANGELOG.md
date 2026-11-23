# Changelog

## 0.1.1 (November 23, 2026)

- README: removed the paragraph about the internal build pipeline. It described files that are not
  part of the package.

## 0.1.0 (November 23, 2026)

First release.

- `TemperatureController` client: system and measuring state, channel and heater settings,
  latest and live measurements, channel and heater history, manual heater power, PID setpoint,
  and access to any other endpoint with `request()`.
- Typed results with decoded measurement status flags.
- Values shown like the controller's screen: five significant digits with an SI prefix, and the
  resistance when a channel has no temperature (`Measurement.display_value`, `format_resistance()`,
  `format_power()`).
- Connection errors name the cause (connection refused, no route to host, name not
  resolved, connect timeout) with a hint for each.
- `bluefors-tc` command-line tool for read-only checks.
- QCoDeS driver (`bluefors_tc.qcodes_driver.BlueforsTC`) in the current QCoDeS driver style: typed
  parameter and channel attributes, typed keyword arguments, and snapshots that don't read measured
  values. Works with QCoDeS 0.50 and newer.
- Examples for reading, streaming, CSV logging, history, heaters, zone PID, QCoDeS and MQTT.
- Python 3.10 or newer on Windows, macOS and Linux.
