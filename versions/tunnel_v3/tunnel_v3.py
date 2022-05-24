# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""

import socket
from ports_def import tcp_ports
from ports_def import udp_ports
import sys
import requests
import struct
import time
import threading
import serial
from datetime import datetime
from modemClass import Modem

side = ""
com_port = ""
try:
    com_port = sys.argv[1]
except:
    com_port = raw_input("please enter a com port e.g COM4 >> ")
    
device_and_speed = [com_port,57600]
opponent = socket.gethostbyname(socket.gethostname())
data = []
HOST = socket.gethostbyname(socket.gethostname())
tcpPort = tcp_ports['slave']
state = "disconnected"
jitterBuff = 0.0
poll_rate = 0.01
sync_delay = 0
start = 0
try:
    opponent = sys.argv[2]
except:
    pass
try:
    if "jitter" in sys.argv:
        jitter = True
except:
    jitter = False

def initConnection(ms):
    
    global opponent
    global start
    # ip = requests.get('https://api.ipify.org').content.decode('utf8')
    ip = str(3)
    #print(f'My IP address is: {ip}')
    if ms == "slave":
        print("I'm slave")
        PORT = tcpPort
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind((HOST, PORT))
        tcp.listen(5)
        conn, addr = tcp.accept()
        while True:
            data = conn.recv(1024)
            if data.split(b'ip')[0] == b'ready':
                conn.sendall(b'g2gip'+(ip))
                print("Sending Ring")
                ser.write("RING\r\n")
                ser.write("CONNECT\r\n")
                # opponent = data.split(b'ip')[1].decode('utf-8')
                print("Ready for Netlink!")
                # print('Opponent IP: %s'% opponent)
                return "connected"
            if not data:
                break
    if ms == "master":
        print("I'm master")
        PORT = tcpPort
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.connect((opponent, PORT))
        tcp.sendall(b"readyip"+(ip))
        data = tcp.recv(1024)
        if data.split(b'ip')[0] == b'g2g':
            # opponent = data.split(b'ip')[1].decode('utf-8')
            print("Ready for Netlink!")
            # print('Opponent IP: %s'% opponent)
            return "connected"
                
    else:
        return "error"



def listener():
    while(state == "connected"):
        try:
            packet = udp.recvfrom(1024)
            message = packet[0]
            payload = message.split(b'sequenceno')[0]
            raw_sequence = message.split(b'sequenceno')[1]
            sequence = struct.unpack('d',raw_sequence)[0]
            if len(payload) > 0:
                print(payload)
            data.append({'ts':sequence,'data':payload})
            
        except KeyboardInterrupt:
            print("Error thread 1")
            sys.exit()
                
def printer():
    global com_port
    global state
    print("I'm the printer")
    while(state == "connected"):
        try:
            read = data.pop(0)
            if jitter == True:
                time.sleep(poll_rate)
            ts = read['ts']
            toSend = read['data']
            latency = round(((time.time() - ts)*1000),0)
            if len(toSend) >0:
                print('latency: %sms' % latency)
                print(toSend)
            else:
                print('empty')
            ser.write(toSend)
        except:
            continue
            
def sender():
    global state
    print("sending")
    if side == "slave":
        oppPort = udp_ports['master']
    if side == 'master':
        oppPort = udp_ports['slave']
    while(state == "connected"):
        raw_input = ser.read(1024)
        # if len(raw_input) == 0:
        #     continue
        if "NO CARRIER" in raw_input:
            state = "disconnected"
            break
        delimiter = "sequenceno"
        try:
            payload = raw_input
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (opponent,oppPort))
        except KeyboardInterrupt:
            sys.exit()
        except ConnectionResetError:
            continue
            
def process():
    #This is nearly identical to the dreampi connection script except for mode == "CONNECTED"
    #This is where you can use digit recognition to branch out to Netlink
    global side

    dial_tone_enabled = "--disable-dial-tone" not in sys.argv

    modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
    
    mode = "LISTENING"

    modem.connect()
    if dial_tone_enabled:
        modem.start_dial_tone()

    time_digit_heard = None

    while True:

        now = datetime.now()

        if mode == "LISTENING":
            modem.update()
            char = modem._serial.read(1).strip()
            if not char:
                continue

            if ord(char) == 16:
                # DLE character
                try:
                    char = modem._serial.read(1)
                    digit = int(char)
                    print("Heard: %s" % digit)

                    mode = "ANSWERING"
                    modem.stop_dial_tone()
                    time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                ts = time.time()
                modem.answer()
                time_to_answer = time.time() - ts
                print('Time to answer: %s' % time_to_answer)
                ts = time.time()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "CONNECTED":
            if digit == 0:
                
                side = "slave"
                return
            if digit == 7:
                side = "master"
                return

process()
print("process says I'm %s" % side)              
t1 = threading.Thread(target=listener)
t2 = threading.Thread(target=printer)
t3 = threading.Thread(target=sender)
ser = serial.Serial(com_port, device_and_speed[1], timeout=poll_rate)
state = initConnection(side)
print(state)
                
if state == "connected":
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind((HOST, udp_ports[side]))
    t1.start()
    t2.start()
    t3.start()
        


