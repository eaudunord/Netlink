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

side = sys.argv[1]
try:
    print(sys.argv[2])
except:
    pass
opponent = ""
data = []
HOST = "127.0.0.1"
tcpPort = tcp_ports['slave']
udpPort = udp_ports[side]
#PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
state = "disconnected"
jitterBuff = 0.04
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind((HOST, udpPort))
sync_delay = 0
start = 0

# with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as udp:
#     udp.bind((HOST, udpPort))

def initConnection(ms):
    global opponent
    global udpPort
    global start
    ip = requests.get('https://api.ipify.org', verify=False).content.decode('utf8')
    #print(f'My IP address is: {ip}')
    if ms == "slave":
        print("I'm slave")
        PORT = tcpPort
        #udpPort = udp_ports['slave']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind((HOST, PORT))
        tcp.listen(5)
        conn, addr = tcp.accept()
        while True:
            data = conn.recv(1024)
            if data.split(b'ip')[0] == b'ready':
                conn.sendall(b'g2gip'+(ip))
                opponent = data.split(b'ip')[1].decode('utf-8')
                print("Ready for Netlink!")
                print('Opponent IP: %s'% opponent)
                ts = time.time()
                start = ts + 0.2 
                conn.sendall(struct.pack('d',ts))
                return "connected"
            if not data:
                break
    if ms == "master":
        print("I'm master")
        PORT = tcpPort
        #udpPort = udp_ports['master']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.connect((HOST, PORT))
        tcp.sendall(b"readyip"+(ip))
        data = tcp.recv(1024)
        if data.split(b'ip')[0] == b'g2g':
            opponent = data.split(b'ip')[1].decode('utf-8')
            print("Ready for Netlink!")
            print('Opponent IP: %s'% opponent)
            ts = tcp.recv(1024)
            st = struct.unpack('d',ts)[0]
            delay = st+0.2-time.time()
            start = delay + time.time()
            return "connected"
                
    else:
        return "error"



def listener():
    while(True):
        try:
            # print("test")
            # time.sleep(1)
            packet = udp.recvfrom(1024)
            message = packet[0]
            payload = message.split(b'sequenceno')[0]
            raw_sequence = message.split(b'sequenceno')[1]
            sequence = struct.unpack('d',raw_sequence)[0]
            data.append({'ts':sequence,'data':payload})
            print(data[-1]['data'])
        except KeyboardInterrupt:
            print("Error thread 1")
            sys.exit()
                
def printer():
    first_run = True
    print("I'm the printer")
    while(True):
        if state != "connected":
            continue
        else:
            # print("printing")
            try:
                read = data.pop(0)
                ts = read['ts']
                toSend = read['data']
                if first_run == True:
                    time.sleep(jitterBuff)
                    first_run = False
                #print(toSend)
                latency = round(((time.time() - ts)*1000),0)
                print('latency: %sms' % latency)
                time.sleep(0.02)
            except:
                #time.sleep(.01)
                continue
            
def sender():
    print("sending")
    if side == "slave":
        oppPort = udp_ports['master']
    if side == 'master':
        oppPort = udp_ports['slave']
    while(state == "connected"):
        raw_input = side
        # delimiter = str.encode("sequenceno",'ANSI')
        delimiter = "sequenceno"
        try:
            # payload = str.encode(raw_input,'ANSI')
            payload = raw_input
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (HOST,oppPort))
            
            time.sleep(.02)
            #raw_input = input(">> ")
        except KeyboardInterrupt:
            sys.exit()
            

                
t1 = threading.Thread(target=listener)
t1.setDaemon(True)
t2 = threading.Thread(target=printer)
t2.setDaemon(True)
t3 = threading.Thread(target=sender)
t3.setDaemon(True)
state = initConnection(side)
print(state)
sync_delay = start-time.time()
time.sleep(sync_delay) 
                
if state == "connected":
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()
        


