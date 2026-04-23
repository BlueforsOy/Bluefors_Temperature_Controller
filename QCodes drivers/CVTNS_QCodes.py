# This Python file uses the following encoding: utf-8
#
import os
from typing import Optional
import subprocess
import time
import json
import websocket
from typing import Any
from qcodes.instrument.base import Instrument

class MWNoiseSource(Instrument):
    """
    This is the QCoDeS driver for BlueFors Cryogenic Microwave Noise Source.
    """

    def __init__(self, name: str, address: str, **kwargs: Any) -> None:
        """
        QCoDeS driver for BlueFors Cryogenic Microwave Noise Source controlled with a BFTC.
        ! This driver gets parameters from BFTC WebSocket API.
        
        """

        
        super().__init__(name=name, **kwargs)
        
        self.IP = address
        self.temperature_channel = 2  # BFTC sensor channel used for CVTNS thermometry
        self.heater_channel = 4       # BFTC heater channel used for CVTNS temperature control
        self.PID_enabled = False
        self.Heater_output = 0
        self.P = 0
        self.I = 0
        self.D = 0

        self.add_parameter(name='Temperature',
                           unit='Kelvin',
                           get_cmd=lambda: self.measure_temperature(),
                           set_cmd=lambda ht: self.set_temperature(ht),
                           docstring='Noise Source Temperature',)

        
    def measure_temperature(self) -> float: #Measure current CVTNS temperature
        ip = self.IP
        TIMEOUT = 60
        ch = 0
        channel = self.temperature_channel
        url = 'ws://' + ip + ':5002/channel/measurement/listen'
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        while channel != ch:
            try:
                resp = ws.recv()
            except websocket.WebSocketTimeoutException:
                print(ip + " timeout")
                continue    
            data = json.loads(resp)
            ch = data["channel_nr"]
            data = json.loads(resp)
        self.Temperature = data["temperature"]
        return data["temperature"]
        
    def measure_mxc_temperature(self) -> float: #Measure current MXC flange temperature
        ip = self.IP
        TIMEOUT = 60
        ch = 0
        channel = 6
        url = 'ws://' + ip + ':5002/channel/measurement/listen'
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        while channel != ch:
            try:
                resp = ws.recv()
            except websocket.WebSocketTimeoutException:
                print(ip + " timeout")
                continue    
            data = json.loads(resp)
            ch = data["channel_nr"]
            data = json.loads(resp)
        self.Temperature = data["temperature"]
        return data["temperature"]
    
    def set_temperature(self,temperature: float) -> None:  #Change CVTNS temperature setpoint
        ip = self.IP
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        a = 2.13709E-5        #a, b -- power curve parameters for ColdPlate mounted CVTNS, must be adjusted.
        b = 2.7726
        Max_Power = 2*a*temperature**b  
        print('Setting temperature to '+str(temperature)+'K')
        
        if 0.0 <= temperature <= 0.2:
            proportional = 0.0001
            integral = 500
            derivative = 0.05
        else:
            if 0.2 < temperature <= 0.500:
                proportional = 0.0001
                integral = 200
                derivative = 0.05
            else:
                if 0.5 < temperature <= 1:
                    proportional = 0.0005
                    integral = 200
                    derivative = 0.05
                else:
                    if 1 < temperature <= 2:
                        proportional = 0.0005
                        integral = 200
                        derivative = 0.05
                    else:
                        if 2 < temperature:
                            proportional = 0.0005
                            integral = 200
                            derivative = 0.05
                            

        channel = self.heater_channel
        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": channel, "active": switch, "pid_mode": PID_switch, "setpoint": temperature, "max_power": Max_Power, "control_algorithm_settings": {"proportional": proportional, "integral": integral, "derivative": derivative}}                 
        ws.send(json.dumps(message))
        ws.close()

    def set_mxc_temperature(self,temperature: float) -> None: #Change MXC flange temperature setpoint
        ip = self.IP
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        a = 0.01997
        b = 1.93013
        Max_Power = 2*a*temperature**b
        print('Setting MXC temperature to '+str(temperature)+'K')
        
        if 0.0 <= temperature <= 0.08:
            proportional = 0.01
            integral = 500
            derivative = 0
        else:
            if 0.08 < temperature <= 0.500:
                proportional = 0.03
                integral = 500
                derivative = 0.05
            else:
                if 0.5 < temperature <= 1:
                    proportional = 0.05
                    integral = 200
                    derivative = 0.05
                else:
                    if 1 < temperature <= 2:
                        proportional = 0.05
                        integral = 200
                        derivative = 0.05
                    else:
                        if 2 < temperature:
                            proportional = 0.05
                            integral = 200
                            derivative = 0.05

        channel = self.heater_channel
        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": channel, "active": switch, "pid_mode": PID_switch, "setpoint": temperature, "max_power": Max_Power, "control_algorithm_settings": {"proportional": proportional, "integral": integral, "derivative": derivative}}                 
        ws.send(json.dumps(message))
        ws.close()

    
    def set_heater_power(self,power: float):    # Set heater power in open loop mode
        TIMEOUT = 10 
        ip = self.IP
        switch = True
        PID_switch = 0
        self.PID_enabled = False
        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": self.heater_channel, "active": switch, "pid_mode": PID_switch, "power": power}                 
        ws.send(json.dumps(message))
        ws.close()

    def set_PID(self,proportional: float,integral: float,derivative: float,) -> None: # Set PID parameters
        ip = self.IP
        self.P = proportional
        self.I = integral
        self.D = derivative
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        print('Updating PID parameters')
        channel = self.heater_channel
        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": channel, "active": switch, "pid_mode": PID_switch, "control_algorithm_settings": {"proportional": proportional, "integral": integral, "derivative": derivative}}                 
        ws.send(json.dumps(message))
        ws.close()