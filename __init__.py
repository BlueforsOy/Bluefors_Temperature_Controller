#Copyright Bluefors Oy 2023

import json
import numpy as np
import websocket
import time
import requests as req

def CS_read_p_flow():
    """
    Reads pressures and flow from CS at local network
    """
    r = req.get('http://localhost:49099/values/mapper/bf/pressures?prettyprint=1')
    data = json.loads(r.content)
    p = []
    for n in range(0, 6):
        p.append(data['data']['mapper.bf.pressures.p' + str(n + 1)]['content']['latest_value']['value'])

    r = req.get('http://localhost:49099/values/mapper/bf/flow?prettyprint=1')
    data = json.loads(r.content)
    p.append(data['data']['mapper.bf.flow']['content']['latest_value']['value'])
    for i in range(0, len(p)):
        if p[i] == '':
            p[i] = '0'
    return p


def set_PID_temperature(temp):
    heat_settings = '{"heater_nr":' + str(ch) + ', "power": ' + str(power) + '}'
    ws = websocket.create_connection('ws://' + ip + ':5002/heater/update', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    ws.close()
    data = json.loads(resp)
    return data


def ht_write(ip, ch, power):
    """
    Changes heater power in manual mode
    ip = TC ip address
    ch = heater channel
    power = heating power in Watts
    returns = JSON string from TC
    """
    heat_settings = '{"heater_nr":' + str(ch) + ', "power": ' + str(power) + '}'
    ws = websocket.create_connection('ws://' + ip + ':5002/heater/update', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    ws.close()
    data = json.loads(resp)
    return data

def ht_setpoint(ip, ch, setpoint):
    heat_settings = '{"heater_nr":' + str(ch) + ', "setpoint": ' + str(setpoint) + '}'
    ws = websocket.create_connection('ws://' + ip + ':5002/heater/update', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    ws.close()
    data = json.loads(resp)
    return data


def thermometer_read(ip):
    ws = websocket.create_connection('ws://' + ip + ':5002/channel/measurement/listen', timeout=30)
    resp = ws.recv()
    data = json.loads(resp)
    return data
    
def thermometer_channel_read(ip, ch_nr):
    read_settings = '{"channel_nr":' + str(ch_nr) +'}'
    ws = websocket.create_connection('ws://' + ip + ':5002/channel', timeout=30)
    ws.send(read_settings)
    resp = ws.recv()
    data = json.loads(resp)
    return data

def heater_read(ip, heater_nr):
    heat_settings = '{"heater_nr":' + str(heater_nr) + '}'
    ws = websocket.create_connection('ws://' + ip + ':5002/heater', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    data = json.loads(resp)
    return data

def heater_parameters(ip, heater_nr, pid_mode, target, max_power, prop, integ, der):
    '''
    :param ip: TC ip address string
    :param heater nr: 1-4 integer
    :param pid_mode = 0 Manual 1 - PID
    :param target = target temperature
    :param max_power = maximum heating power
    :param prop = P in PID
    :param int = I in PID
    :param der = D in PID
    :return: -
    '''
    #print('here')
    heat_settings = '{"heater_nr":' + str(heater_nr) + \
                    ', "pid_mode":' + str(pid_mode) + ', "max_power":' + str(max_power)\
                    + ', "setpoint": ' + str(target) + \
                    ', "control_algorithm_settings": {"proportional": ' + str(prop)+\
                    ', "integral": ' + str(integ)+\
                    ', "derivative": ' + str(der)+\
                    '} }'
    print(heat_settings)
    ws = websocket.create_connection('ws://' + ip + ':5002/heater/update', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    data = json.loads(resp)
    return data


def heater_switch(ip, heater_nr, state):
    '''

    :param ip: TC ip address string
    :param heater nr: 1-4 integer
    :param state: 'true'/'false' boolean
    :return: -
    '''

    if state:
        state = 'true'
    else:
        state = 'false'
    heat_settings = '{"heater_nr":' + str(heater_nr) + ', "active":' + str(state) + '}'
    #print(heat_settings)
    ws = websocket.create_connection('ws://' + ip + ':5002/heater/update', timeout=10)
    ws.send(heat_settings)
    resp = ws.recv()
    data = json.loads(resp)
    return data


def last_temperature(ip):
    ws = websocket.create_connection('ws://' + ip + ':5002/channel/measurement/listen', timeout=30)
    resp = ws.recv()
    data = json.loads(resp)
    return data['temperature']


def thermometer_read_hist(ip, ch, time = 10):
    """
    Reads data of TC channel backwards from present time 
    ch = TC channel 
    time = how many seconds from history the data is retrieved
    """
    #Reads first current time from TC
    r = req.get('http://' + ip + ':5001/system', timeout=10)
    #wsys = websocket.create_connection('ws://' + ip + ':5002/system', timeout=30)
    time_now = r.json()['datetime']
    print(time_now)
    #time_now = timedata['datetime']
    timestamp_now = datetime.strptime(time_now.rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f")
    #Remove microseconds
    #timestamp_now = dt.replace(microsecond=0).isoformat()
    time_now = timestamp_now.replace(microsecond=0).isoformat()
    #Subtract time seconds
    timestamp_past = timestamp_now - timedelta(seconds = time)
    #Create datetime string
    time_past = timestamp_past.replace(microsecond=0).isoformat()

    channel_nr = ch
    fields = '["temperature", "timestamp"]'

                                          
    read_hist = '{"channel_nr":' + str(channel_nr) + ',' \
        '"start_time": "' + time_past + '", ' \
        '"stop_time": "' + time_now + '", ' \
        '"fields":' + fields + '}'
    #print(read_hist)
    
    ws = websocket.create_connection('ws://' + ip + ':5002/channel/historical-data', timeout=30)
    ws.send(read_hist)
    resp = ws.recv()
    #print(resp)
    data = json.loads(resp)
    return data
    
def read_all_thermo(ip):
    """
    Reads current values of all active thermometers. Reading takes full scanning cycle.
    returns: 
    """
    data = []
    lista = []
    try:
        r = thermometer_read(ip)

        first = r['channel_nr']
        lista.append(first)
        data.append(r)
        while True:
            r = thermometer_read(ip)
            if first == r['channel_nr']:
                break
            lista.append(r['channel_nr'])
            data.append(r)
        return lista, data
    except:
        return [], []

def temperature_stable(T_set, ip):
    """
    Waits for temperature to stabilize to T_set, in channel. Works when only one channel is measured
    T_set: target temperature in K
    ip: TC device ip address
    :return: Boolean
    """
    mem = np.zeros(5)
    stable = False
    while not stable:
        k=0
        for ind, t in enumerate(mem):
            temp = thermometer_read(ip)['temperature']
            mem[ind]=temp
            #print(mem)

            st_dev = np.std(mem)
            st_mean = np.mean(mem)
            #print(mem)
            #print(st_dev, st_mean)
            #print(temp, st_mean, st_dev)

            if abs(T_set-st_mean) < 0.01 and abs(st_dev) < 0.005:
            #if T_set - temp < 0.1:
                stable = True
            time.sleep(0)
    return stable

# ================= PARAMETERS ============================

ip1 = '10.10.20.196'  # BF TC 1
ip2 = '10.10.20.197'  # BF TC 2


if __name__ == '__main__':

    print(thermometer_read_hist(ip1, 1, 200))
'''
ht_setpoint(ip2, 1, 2.900)
print(heater_read(ip2, 1))
heater_switch(ip2, 1, True)
#lista2, data2 = read_all_thermo(ip2)
for _ in range(10):
    print(last_temperature(ip1), last_temperature(ip2))
'''