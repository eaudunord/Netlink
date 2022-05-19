# -*- coding: utf-8 -*-
"""
Created on Tue May 17 21:03:28 2022

@author: selln
"""

import socket
import time
import struct
import sys
import threading
from threading import *

localIP     = "127.0.0.1"

localPort   = 20001

bufferSize  = 1024

UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

UDPServerSocket.bind((localIP, localPort))
serverAddressPort   = ("127.0.0.1", 20002)


listening = True

send_rcv = False
data=[]
def listener():
    global send_rcv
    global localIP
    global localPort
    global bufferSize
    global UDPServerSocket
    global serverAddressPort
    print("UDP server up and listening")
    connecting = True
    while(connecting == True):
        try:
            # UDPServerSocket.sendto(b'Ready', serverAddressPort)
            ready = UDPServerSocket.recvfrom(bufferSize)
            print(ready)
            if ready[0] == b'Ready':
                ack = str.encode('ack')
                UDPServerSocket.sendto(ack, serverAddressPort)
                send_rcv = True
                break
            #time.sleep(1)
        except KeyboardInterrupt:
            sys.exit()
    while(True):
        try:
            bytesAddressPair = UDPServerSocket.recvfrom(bufferSize)
            # global first_run
            # if first_run == True:
            #     time.sleep(.02)
            #     first_run = False
            if bytesAddressPair[0] == b'Ready':
                continue
            message = bytesAddressPair[0]
    
            address = bytesAddressPair[1]
    
            clientMsg = "Message from Client:{}".format(message)
        #clientIP  = "Client IP Address:{}".format(address)
        
        # print(bytesAddressPair[0])
            payload = message.split(b'sequenceno')[0]
            raw_sequence = message.split(b'sequenceno')[1]
            sequence = struct.unpack('d',raw_sequence)[0]
            data.append({'ts':sequence,'data':payload})
            print(data[-1]['data'])
            # print(payload)
            
            
            # print(sequence)
            
        #print(clientIP)
        except KeyboardInterrupt:
            UDPServerSocket.close()
            print("Error thread 1")
            sys.exit()
            
def printer():
    first_run = True
    print("I'm thread 2")
    while(True):
        if send_rcv == False:
            continue
        else:
            print(send_rcv)
            try:
                read = data.pop(0)
                ts = read['ts']
                toSend = read['data']
                if first_run == True:
                    time.sleep(0.04)
                    first_run = False
                print(toSend)
                latency = round(((time.time() - ts)*1000),0)
                print(latency)
                time.sleep(0.02)
            except:
                #time.sleep(.01)
                continue
        # if (len(data) > 0):
        #     try:            
        #         latency = round(((time.time() - data['ts'])*1000),0)
        #         print(latency)
        #         x = data.pop(0)['data']
        #         print(x)
        #         time.sleep(0.01)
        #     except:
        #         continue
def sender():
    global send_rcv
    global localIP
    global localPort
    global bufferSize
    global serverAddressPort
    global UDPServerSocket
    print("Master Side Initialized")
    while(True):
        if send_rcv == False:
            continue
        else:
            
            raw_input = "Master"
            
            delimiter = str.encode("sequenceno",'ANSI')
            while(send_rcv == True):
                try:
                    payload = str.encode(raw_input,'ANSI')
                    ts = time.time()
                    UDPServerSocket.sendto((payload+delimiter+struct.pack('d',ts)), serverAddressPort)
                    
                    time.sleep(.02)
                    #raw_input = input(">> ")
                except KeyboardInterrupt:
                    sys.exit()
t1 = threading.Thread(target=listener, daemon=True)
t2 = threading.Thread(target=printer, daemon=True)
t3 = threading.Thread(target=sender, daemon=True)
t1.start()
t2.start()
t3.start()
t1.join()
t2.join()
t3.join()