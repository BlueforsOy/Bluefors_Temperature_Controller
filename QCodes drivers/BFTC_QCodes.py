# This Python file uses the following encoding: utf-8
#   
import os
from typing import Optional
import subprocess
import time
import json
import websocket

from qcodes.instrument.base import Instrument

class BFTC(Instrument):
    """
    This is the QCoDeS driver example for BlueFors Temperature Controller (BFTC).
    For educational purposes only.
    """

    def __init__(self, name: str, IP: str, **kwargs) -> None:
        """
        QCoDeS driver for BlueFors Temperature Controller (BFTC).
        ! This driver gets parameters from BFTC WebSocket API.
        
        """

        
        super().__init__(name=name, **kwargs)
        
        self.IP = IP        # BFTC IP address 

        self.add_parameter(name='Ch1_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(1),
                           docstring='Channel 1 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch2_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(2),
                           docstring='Channel 2 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch3_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(3),
                           docstring='Channel 3 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch4_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(4),
                           docstring='Channel 4 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch5_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(5),
                           docstring='Channel 5 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch6_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(6),
                           docstring='Channel 6 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch7_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(7),
                           docstring='Channel 7 Temperature',)   # Temperature parameter
        
        self.add_parameter(name='Ch8_Temperature',
                           unit='Kelvin',
                           get_parser=float,
                           get_cmd=lambda: self.measure_temperature(8),
                           docstring='Channel 8 Temperature',)   # Temperature parameter


        
    def measure_temperature(self, channel_num: int) -> float:         #Measure the temperature.
        ip = self.IP
        TIMEOUT = 60
        ch = 0
        url = 'ws://' + ip + ':5002/channel/measurement/listen'
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        while channel_num != ch:
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
    
    def set_PID(self,heater_num: int, temperature: float) -> None:       #Set the temperature using PID mode
        ip = self.IP
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        a = 2.13709E-5                      #a, b -- power curve parameters for LD system MXC flange, must be adjusted.
        b = 2.7726                          
        Max_Power = 1.2*a*temperature**b    #Maximum output power for a setpoint. Power curve parameters must be adjusted.
        if Max_Power > 3e-3: Max_Power = 3e-3
        
        #Zone PID implementation 
        
        if 0.0 <= temperature <= 0.08:           #parameters for 0 to 80mK
            proportional = 0.01
            integral = 500
            derivative = 0
        else:
            if 0.8 < temperature <= 0.500:      #parameters for 80mK to 500mK
                proportional = 0.03
                integral = 500
                derivative = 0.05
            else:
                if 0.5 < temperature <= 1:      #parameters for 500mK to 1K
                    proportional = 0.05
                    integral = 200
                    derivative = 0.05
                else:
                    if 1 < temperature <= 2:    #parameters for 1K to 2K
                        proportional = 0.05
                        integral = 200
                        derivative = 0.05
                    else:
                        if 2 < temperature:     #parameters for 2K and higher
                            proportional = 0.05
                            integral = 200
                            derivative = 0.05

        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": heater_num, "active": switch, "pid_mode": PID_switch, "setpoint": temperature, "max_power": Max_Power, "control_algorithm_settings": {"proportional": proportional, "integral": integral, "derivative": derivative}}                 
        ws.send(json.dumps(message))
        ws.close()
    
    def set_heater_power(self,heater_num,power: float):        #Set the NS heater power output directly, without PID.
        TIMEOUT = 10 
        ip = self.IP
        switch = True
        PID_switch = 0
        self.PID_enabled = False
        if power > 3e-3: power = 3e-3
        url = "ws://" + ip + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": heater_num, "active": switch, "pid_mode": PID_switch, "power": power}                 
        ws.send(json.dumps(message))
        ws.close()
