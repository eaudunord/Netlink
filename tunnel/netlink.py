# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
import sys

if __name__ == "__main__":
    print("This script should not be run on its own")
    sys.exit()

import socket
import time
import serial
from datetime import datetime
import logging
logger = logging.getLogger('dreampi')
import threading
import binascii
import select

packetSplit = "<packetSplit>"
dataSplit = "<dataSplit>"
printout = False
if 'printout' in sys.argv:
    printout = True
timeout = 0.003
data = []
state = "starting"
poll_rate = 0.01
ser = ""

def digit_parser(modem):
    char = modem._serial.read(1)
    tel_digits = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
    ip_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9','*']
    if char in tel_digits:
        return {'client':'ppp_internet','dial_string':char,'side':'na'}
    elif char == '0':
        return {'client':'direct_dial','dial_string':char,'side':'slave'}
    elif char == '#':
        dial_string = ""
        while (True):
            char = modem._serial.read(1)
            if not char:
                continue
            if ord(char) == 16: #16 is DLE
                try:
                    char = modem._serial.read(1)
                    if char == '#':
                        if '*' in dial_string:
                            break
                        elif len(dial_string) == 12:
                            dial_string = '.'.join(dial_string[i:i+3] for i in range(0, len(dial_string), 3))
                            break
                    if char in ip_digits:
                        dial_string += char
                except (TypeError, ValueError):
                    pass
        return {'client':'direct_dial','dial_string':dial_string,'side':'master'}
    else:
        return "nada"

def initConnection(ms,dial_string):
    opponent = dial_string.replace('*','.')
    if ms == "slave":
        logger.info("I'm slave")
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(120)
        tcp.bind(('', PORT))
        tcp.listen(5)
        ready = select.select([tcp], [], [])
        if ready[0]:
            conn, addr = tcp.accept()
            opponent = addr[0]
            logger.info('connection from %s' % opponent)
            while True:
                try:
                    data = conn.recv(1024)
                except socket.error: #first try can return no payload
                    continue
                if data == b'ready':
                    conn.sendall(b'g2g')
                    logger.info("Sending Ring")
                    ser.write("RING\r\n")
                    ser.write("CONNECT\r\n")
                    logger.info("Ready for Netlink!")
                    tcp.shutdown(socket.SHUT_RDWR)
                    tcp.close()
                    return ["connected",opponent]
                if not data:
                    print("failed to init")
                    tcp.shutdown(socket.SHUT_RDWR)
                    tcp.close()
                    break
    if ms == "master":
        logger.info("I'm master")
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(120)
        tcp.connect((opponent, PORT))
        tcp.sendall(b"ready")
        ready = select.select([tcp], [], [])
        if ready[0]:
            data = tcp.recv(1024)
            if data == b'g2g':
                logger.info("Ready for Netlink!")
                tcp.shutdown(socket.SHUT_RDWR)
                tcp.close()
                return ["connected",opponent]
                
    else:
        return ["error","error"]




            

         


def netlink_setup(device_and_speed,side,dial_string):
    global ser
    ser = serial.Serial(device_and_speed[0], device_and_speed[1], timeout=timeout)
    state = initConnection(side,dial_string)
    time.sleep(0.2)
    return state

def netlink_exchange(side,net_state,opponent):
    def listener():
        print(state)
        last = 0
        currentSequence = 0
        while(state != "netlink_disconnected"):
            ready = select.select([udp],[],[],0.003)
            if ready[0]:
                packetSet = udp.recv(1024)
                packets= packetSet.split(packetSplit)
                try:
                    while True:
                        packetNum = 0
                        
                        #go through all packets 
                        for p in packets:
                          if int(p.split(dataSplit)[1]) == currentSequence:
                            break
                          packetNum += 1
                        
                        #if the packet needed is not here,  grab the latest in the set
                        if packetNum == len(packets):
                            packetNum = 0
                        
                        message = packets[packetNum]
                        payload = message.split(dataSplit)[0]
                        sequence = message.split(dataSplit)[1]
                        if int(sequence) < currentSequence:
                            break  #All packets are old data, so drop it entirely
                        
                        currentSequence = int(sequence) + 1
                        
                        toSend = payload
                        
                        ser.write(toSend)
                        if len(payload) > 0 and printout == True:
                            logger.info(binascii.hexlify(payload))
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except IndexError:
                    continue
                    
        logger.info("listener stopped")        
                
    def sender(side,opponent):
        global state
        logger.info("sending")
        first_run = False
        oppPort = 20002
        last = 0
        sequence = 0
        packets = []
        
        while(state != "netlink_disconnected"):
            if ser.in_waiting > 0:
                if first_run == True:
                    raw_input = ser.read(1024) #crude buffer empty
                    first_run = False
                    raw_input = ser.read(ser.in_waiting)
                else:
                    raw_input = ser.read(ser.in_waiting)
                if "NO CARRIER" in raw_input:
                    logger.info("detected hangup")
                    state = "netlink_disconnected"
                    time.sleep(1)
                    udp.close()
                    ser.flush()
                    ser.close()
                    logger.info("sender stopped")
                    return
                
                try:
                    payload = raw_input
                    seq = str(sequence)
                    if len(payload)>0:
                        
                        packets.insert(0,(payload+dataSplit+seq))
                        if(len(packets) > 5):
                            packets.pop()
                            
                        for i in range(2): #send the data twice. May help with drops or latency    
                            ready = select.select([],[udp],[])   
                            if ready[1]:
                                udp.sendto(packetSplit.join(packets), (opponent,oppPort))
                                    
                        sequence+=1
                except:
                    continue

    global state 
    state = net_state              
    if state == "connected":
        t1 = threading.Thread(target=listener)
        t2 = threading.Thread(target=sender,args=(side,opponent))
        Port = 20002
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setblocking(0)
        udp.bind(('', Port))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        


