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
opponent = ""
data = []
HOST = "127.0.0.1"
tcpPort = tcp_ports['slave']
udpPort = udp_ports[side]
#PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
state = "disconnected"
jitterBuff = 0.04

with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as udp:
    udp.bind((HOST, udpPort))

def initConnection(side):
    global opponent
    global udpPort
    ip = requests.get('https://api.ipify.org', verify=False).content.decode('utf8')
    #print(f'My IP address is: {ip}')
    if side == "slave":
        print("I'm slave")
        PORT = tcpPort
        #udpPort = udp_ports['slave']
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.bind((HOST, PORT))
            tcp.listen()
            conn, addr = tcp.accept()
            with conn:
                while True:
                    data = conn.recv(1024)
                    if data.split(b'ip')[0] == b'ready':
                        conn.sendall(b'g2gip'+str.encode(ip))
                        opponent = data.split(b'ip')[1].decode('utf-8')
                        print("Ready for Netlink!")
                        print(f'Opponent IP: {opponent}')
                        return "connected"
                    if not data:
                        break
    if side == "master":
        print("I'm master")
        PORT = tcpPort
        #udpPort = udp_ports['master']
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.connect((HOST, PORT))
            tcp.sendall(b"readyip"+str.encode(ip))
            data = tcp.recv(1024)
            if data.split(b'ip')[0] == b'g2g':
                opponent = data.split(b'ip')[1].decode('utf-8')
                print("Ready for Netlink!")
                print(f'Opponent IP: {opponent}')
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
                print(latency)
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
        delimiter = str.encode("sequenceno",'ANSI')
        try:
            payload = str.encode(raw_input,'ANSI')
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (HOST,oppPort))
            
            time.sleep(.02)
            #raw_input = input(">> ")
        except KeyboardInterrupt:
            sys.exit()
            

                
t1 = threading.Thread(target=listener, daemon=True)
t2 = threading.Thread(target=printer, daemon=True)
t3 = threading.Thread(target=sender, daemon=True)
state = initConnection(side)
print(state)
                
if state == "connected":
    t1.start()
    t2.start()
    t3.start()
    t1.join()
    t2.join()
    t3.join()
        


