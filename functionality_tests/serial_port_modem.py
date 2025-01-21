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
from modem import Modem as Modem

ser = serial.Serial('COM5', 9600, timeout=1)  # open serial port
print(ser.name)         # check which port was really used
ser.write(b'hello\r\n')     # write a string

payload = []
i=0
poll = True
now = time.time()
while (poll == True):
    data = ser.read(1)
    # print(data)
    interval = (time.time()-now)*1000
    print(interval)
    now = time.time()
    # payload.append(data)
    i+=1
    if data == b'+':
        ser.close()
        print('serial port closed')
        poll = False
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