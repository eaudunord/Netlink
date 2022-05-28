# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""

import socket
# from ports_def import tcp_ports
# from ports_def import udp_ports
import sys
import requests
import struct
import time
import threading
import random
import logging

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger('dreampi')
side = ""
try:
    side = sys.argv[1]
except:
    pass
if side == "":
    side = raw_input("Side >> ")
    
try:
    print(sys.argv[2])
except:
    pass

HOST = "127.0.0.1"
data = []
tcpPort = 65432
# udpPort = udp_ports[side]
#PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
state = "disconnected"
jitterBuff = 0.01
rate = 1.0
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

sync_delay = 0
start = 0
opponent = "127.0.0.1"

# with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as udp:
#     udp.bind((HOST, udpPort))

def initConnection(ms=side,opponent=opponent,start=start):
    # global opponent
    # # global udpPort
    # global start
    if ms == "slave":
        logger.info("I'm slave")
        PORT = 65432
        #udpPort = udp_ports['slave']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind((HOST, PORT))
        tcp.listen(5)
        conn, addr = tcp.accept()
        while True:
            data = conn.recv(1024)
            if data.split(b'ip')[0] == b'ready':
                conn.sendall(b'g2gip')
                opponent = addr[0]
                print("Ready for Netlink!")
                print('Opponent IP: %s'% opponent)
                ts = time.time()
                start = ts + 0.2 
                conn.sendall(struct.pack('d',ts))
                tcp.close()
                return "connected"
            if not data:
                break
    if ms == "master":
        print("I'm master")
        PORT = 65432
        #udpPort = udp_ports['master']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.connect((opponent, PORT))
        tcp.sendall(b"readyip")
        data = tcp.recv(1024)
        if data.split(b'ip')[0] == b'g2g':
            # opponent = data.split(b'ip')[1].decode('utf-8')
            print("Ready for Netlink!")
            print('Opponent IP: %s'% opponent)
            ts = tcp.recv(1024)
            st = struct.unpack('d',ts)[0]
            delay = st+0.2-time.time()
            start = delay + time.time()
            tcp.close()
            return "connected"
                
    else:
        return "error"



def listener():
    while(True):
        try:
            # print("test")
            # time.sleep(1)
            packet = udp.recvfrom(1024)
            # time.sleep(float((random.randint(0, 6)))/1000) #simulate network jitter
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
                time.sleep(0.01)
                ts = read['ts']
                toSend = read['data']
                # if first_run == True:
                #     # time.sleep(jitterBuff)
                #     first_run = False
                #print(toSend)
                latency = round(((time.time() - ts)*1000),0)
                print('latency: %sms' % latency)
                # time.sleep(rate)
            except:
                # time.sleep(rate)
                continue
            
def sender():
    print("sending")
    if side == "slave":
        oppPort = 20001
    if side == 'master':
        oppPort = 20002
    while(state == "connected"):
        raw_input = side
        # delimiter = str.encode("sequenceno",'ANSI')
        delimiter = "sequenceno"
        try:
            # payload = str.encode(raw_input,'ANSI')
            payload = raw_input
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (opponent,oppPort))
            
            time.sleep(rate)
            #raw_input = input(">> ")
        except KeyboardInterrupt:
            sys.exit()
        except ConnectionResetError:
            continue
            

                
t1 = threading.Thread(target=listener)
# t1.setDaemon(True)
t2 = threading.Thread(target=printer)
# t2.setDaemon(True)
t3 = threading.Thread(target=sender)
# t3.setDaemon(True)
state = initConnection(side)
print(state)
sync_delay = start-time.time()
# time.sleep(sync_delay) 
                
if state == "connected":
    if side == "slave":
        Port = 20002
    if side == 'master':
        Port = 20001

    udp.bind((HOST, Port))
    t1.start()
    t2.start()
    t3.start()
    # t1.join()
    # t2.join()
    # t3.join()
        


