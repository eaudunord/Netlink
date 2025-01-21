# -*- coding: utf-8 -*-
"""
Created on Tue May 17 19:57:29 2022

@author: selln
"""

import os
import serial
from datetime import datetime
from datetime import timedelta
import time
import threading


ser = serial.Serial('COM5', 9600, timeout=0.01)  # open serial port
print(ser.name)         # check which port was really used
ser.write(b'hello\r\n')     # write a string

payload = []
i=0
poll = True
t = False
now = time.time()
time.sleep(5)
def read():
    global poll
    global now
    global t
    while (t == True):
        data = ser.read(1)
        print(data)
        interval = (time.time()-now)*1000
        # print(interval)
        now = time.time()
        # payload.append(data)
        # i+=1
        if data == '+':
            poll = False

def write():
    global poll
    global t
    while (t == True):
        ser.write('write')
        time.sleep(0.01)
t1 = threading.Thread(target=read)
# t1.setDaemon(True)
t2 = threading.Thread(target=write)
# t2.setDaemon(True)
t1.start()
t2.start()
print('threads started')
time.sleep(5)
t = True
if poll == False:
    ser.close()
    print('serial port closed')
# print(payload)

# import socket

# localIP     = "127.0.0.1"

# localPort   = 20002

# bufferSize  = 1024

# serverAddressPort   = ("127.0.0.1", 20001)
# UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
# UDPServerSocket.bind((localIP, localPort))
# print("UDP server up and listening")
# i=0
# sending = True
# while(i<5):
#     UDPServerSocket.sendto(payload[i], serverAddressPort)
#     i+=1
# if i>=5:
#     print("closing socket")
#     UDPServerSocket.close()