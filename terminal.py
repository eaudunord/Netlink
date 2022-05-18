# -*- coding: utf-8 -*-
"""
Created on Wed May 18 08:03:07 2022

@author: joe
"""

import socket
import struct
import time
import sys

localIP     = "127.0.0.1"

localPort   = 20002

bufferSize  = 1024

serverAddressPort   = ("127.0.0.1", 20001)
UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
UDPServerSocket.bind((localIP, localPort))
print("UDP server up and listening")
i= 0
# raw_input = input(">> ")
raw_input = "Test"

delimiter = str.encode("sequenceno",'ANSI')
while(raw_input != "+++"):
    try:
        payload = str.encode(raw_input,'ANSI')
        ts = time.time()
        print(ts)
        UDPServerSocket.sendto((payload+delimiter+struct.pack('d',ts)), serverAddressPort)
        i+=1
        time.sleep(.02)
        #raw_input = input(">> ")
    except KeyboardInterrupt:
        sys.exit()
        
print("closing socket")
UDPServerSocket.close()