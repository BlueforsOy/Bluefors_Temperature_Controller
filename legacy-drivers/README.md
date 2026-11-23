# Bluefors Temperature Controller (BFTC) Python Driver

This repository provides official minimalistic Python driver example for the Bluefors Temperature Controller (BFTC). The driver supports temperature readout, heater power control in open-loop mode and PID-based temperature regulation in closed-loop mode. Two variants are available: with and without QCoDeS integration.

# Example code (without QCodes)

```py

BFTC1 = BFTC('BFTC1','192.168.1.1') # Connect to the instrument;

BFTC1.channels[0].name # Read channel #1 name;

BFTC1.channels[0].get() # Read channel #1 temperature;

BFTC1.set_heater_power(heater_num = 4,power = 1e-6) # Set MXC heater power to 1 uW (open loop operation);

BFTC1.set_PID(heater_num = 4, temperature = 0.050) # Set MXC temperature to 50mK with PID control (closed loop operation);
```

# Example code (QCodes)

```py
# QCodes example. The driver file must be blased to the "..\qcodes\instrument_drivers\Bluefors" folder

# Import BFTC driver
import qcodes.instrument_drivers.Bluefors.BFTC as BF_TC  

# Connect to the instrument;
BFTC1 = BF_TC.BFTC('BFTC_1','192.168.1.1') 

# Temperature measurement function;
BFTC1.Ch1_Temperature.get() 

# Set temperature of a sensor-heater pair using PID temerature control. 
# Preferred PID parameters might need to be adjusted in the driver.
#(-heater channel-, -temeperature in K-)
BFTC1.set_PID(4,1)

# Set the Noise Source heater power output directly without PID. Units: Watts
#(-heater channel-, -power in W-)
TC.set_heater_power(4,1e-6)

# Check if PID temperature control is enebled.
NS.PID_enabled

```
