# -*- coding: utf-8 -*-
"""
Created on Tue May 17 21:03:28 2022

@author: selln
"""

import socket
import time

localIP     = "127.0.0.1"

localPort   = 20001

bufferSize  = 1024

UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)

UDPServerSocket.bind((localIP, localPort))
print("UDP server up and listening")
i=0
listening = True
payload = []
first_run = True
while(i < 5):

    bytesAddressPair = UDPServerSocket.recvfrom(bufferSize)
    time.sleep(10)
    message = bytesAddressPair[0]

    address = bytesAddressPair[1]

    clientMsg = "Message from Client:{}".format(message)
    #clientIP  = "Client IP Address:{}".format(address)
    
    print(message)
    #print(clientIP)
    i+=1
if i>=5:
    print("closing socket")
    UDPServerSocket.close()