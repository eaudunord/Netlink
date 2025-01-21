# -*- coding: utf-8 -*-
"""
Created on Wed May 18 19:20:40 2022

@author: selln
"""

import socket
import struct
import time
import sys
import threading

localIP     = "127.0.0.1"
    
localPort   = 20002
    
bufferSize  = 1024
    
serverAddressPort   = ("127.0.0.1", 20001)
UDPServerSocket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
UDPServerSocket.bind((localIP, localPort))

send_rcv = False
def sender():
    global send_rcv
    global localIP
    global localPort
    global bufferSize
    global serverAddressPort
    global UDPServerSocket
    print("Slave Side Initialized")
    while(True):
        try:
            print("connecting")
            readystr = str.encode('Ready')
            print(readystr)
            UDPServerSocket.sendto(readystr, serverAddressPort)
            #time.sleep(1)
            ack = UDPServerSocket.recvfrom(bufferSize)[0]
            print(ack)
            if (ack == b'ack') :  
                send_rcv = True
                break
            time.sleep(2)
        except KeyboardInterrupt:
            sys.exit()
        except:
            time.sleep(0.02)
            continue
    raw_input = "Slave"
    
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

data=[]
def listener():
    global send_rcv
    global localIP
    global localPort
    global bufferSize
    global serverAddressPort
    global UDPServerSocket
    print("UDP server up and listening")
    while(True):
        if send_rcv == False:
            continue
        else:
            print('listening')
            try:
                bytesAddressPair = UDPServerSocket.recvfrom(bufferSize)
                # global first_run
                # if first_run == True:
                #     time.sleep(.02)
                #     first_run = False
                # if bytesAddressPair[0] == b'Ready':
                #     continue
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
t1 = threading.Thread(target=sender, daemon=True)
t2 = threading.Thread(target=listener, daemon=True)
t3 = threading.Thread(target=printer, daemon=True)
t1.start()
t2.start()
t3.start()
t1.join()
t2.join()
t3.join()
       
# print("closing socket")
# UDPServerSocket.close()