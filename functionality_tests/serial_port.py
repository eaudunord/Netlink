# -*- coding: utf-8 -*-
"""
Created on Tue May 17 19:57:29 2022

@author: selln
"""

import serial
import time
import json

ser = serial.Serial('COM5', 9600, timeout=10)  # open serial port
print(ser.name)         # check which port was really used
ser.write(b'hello')     # write a string

payload = []
i=0
poll = True
while (poll == True):
    data = ser.read(1024)
    print(data)
    payload.append(data)
    i+=1
    if i >= 5:
        ser.close()
        print('serial port closed')
        poll = False
print(payload)

import socket

localIP     = "127.0.0.1"

localPort   = 20002

bufferSize  = 1024

serverAddressPort   = ("127.0.0.1", 20001)
UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
UDPServerSocket.bind((localIP, localPort))
print("UDP server up and listening")
i=0
sending = True
while(i<5):
    UDPServerSocket.sendto(payload[i], serverAddressPort)
    i+=1
if i>=5:
    print("closing socket")
    UDPServerSocket.close()