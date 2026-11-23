import json
import websocket

class Parameter():
    def __init__(self, name, unit, get_cmd):
        self.name = name
        self.unit = unit
        self.get_cmd = get_cmd
    def set(self,set_value):
        self.value = set_value
    def get(self):
        return self.get_cmd()

class BFTC():
    def __init__(self, name, ip_address):
        self.name = name
        self.ip_address = ip_address
        self.PID_enabled = False
        self.Heater_output = 0
        self.P = 0
        self.I = 0
        self.D = 0
        
        self.channels = []
        self.channels.append(Parameter(name = 'Channel 1', unit = 'K', get_cmd = lambda: self.measure_temperature(1)))
        self.channels.append(Parameter(name = 'Channel 2', unit = 'K', get_cmd = lambda: self.measure_temperature(2)))
        self.channels.append(Parameter(name = 'Channel 3', unit = 'K', get_cmd = lambda: self.measure_temperature(3)))
        self.channels.append(Parameter(name = 'Channel 4', unit = 'K', get_cmd = lambda: self.measure_temperature(4)))
        self.channels.append(Parameter(name = 'Channel 5', unit = 'K', get_cmd = lambda: self.measure_temperature(5)))
        self.channels.append(Parameter(name = 'Channel 6', unit = 'K', get_cmd = lambda: self.measure_temperature(6)))
        self.channels.append(Parameter(name = 'Channel 7', unit = 'K', get_cmd = lambda: self.measure_temperature(7)))
        self.channels.append(Parameter(name = 'Channel 8', unit = 'K', get_cmd = lambda: self.measure_temperature(8)))
        
    def measure_temperature(self, channel_num: int) -> float:            #Measure the temperature.
        TIMEOUT = 60
        ch = 0
        url = 'ws://' + self.ip_address + ':5002/channel/measurement/listen'
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
    
    def set_heater_power(self,heater_num,power: float):        #Set the MXC heater power output directly, without PID.
        TIMEOUT = 10 
        switch = True
        PID_switch = 0
        self.PID_enabled = False
        if power > 3e-3: power = 3e-3
        url = "ws://" + self.ip_address + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": heater_num, "active": switch, "pid_mode": PID_switch, "power": power}                 
        ws.send(json.dumps(message))
        ws.close()
        
    def set_PID(self,heater_num: int, temperature: float) -> None:       #Set the temperature using PID mode
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        a = 2.13709E-5                      # a, b -- power curve parameters for an empty LD system MXC flange, should be adjusted based on a power sweep (heater power vs stable MXC temperature).
        b = 2.7726                          
        Max_Power = 1.2*a*temperature**b    # Maximum output power for a setpoint. Power curve parameters should be adjusted to the individual system for better performance.
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

        url = "ws://" + self.ip_address + ":5002/heater/update"
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": heater_num, "active": switch, "pid_mode": PID_switch, "setpoint": temperature, "max_power": Max_Power, "control_algorithm_settings": {"proportional": proportional, "integral": integral, "derivative": derivative}}                 
        ws.send(json.dumps(message))
        ws.close()
