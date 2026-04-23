import json
import websocket
 
class CVTNS():
    def __init__(self, name, ip_address, temperature_channel, heater_channel):
        self.name = name
        self.ip_address = ip_address
        self.temperature_channel = temperature_channel
        self.heater_channel = heater_channel
        self.PID_enabled = False
        self.Heater_output = 0
        self.P = 0
        self.I = 0
        self.D = 0
    
    def measure_temperature(self) -> float:
        ip = self.ip_address
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
        
    def measure_mxc_temperature(self) -> float:
        ip = self.ip_address
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
    
    def set_temperature(self,temperature: float) -> None:
        ip = self.ip_address
        switch = True
        PID_switch = 1
        self.PID_enabled = True
        TIMEOUT = 10
        a = 1.9667923707796934e-05
        b = 2.365472891444369
        Max_Power = 3*a*temperature**b
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

    def set_mxc_temperature(self,temperature: float) -> None:
        ip = self.ip_address
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

    
    def set_heater_power(self,power: float):  
        TIMEOUT = 10 
        ip = self.ip_address
        switch = True
        PID_switch = 0
        self.PID_enabled = False
        url = "ws://" + ip + ":5002/heater/update" 
        ws = websocket.create_connection(url, timeout=TIMEOUT)
        message =  {"heater_nr": self.heater_channel, "active": switch, "pid_mode": PID_switch, "power": power}                 
        ws.send(json.dumps(message))
        ws.close()

    def set_PID(self,proportional: float,integral: float,derivative: float,) -> None:
        ip = self.ip_address
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