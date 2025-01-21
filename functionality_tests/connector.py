# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""

import socket
from ports_def import tcp_ports
import sys
import requests
import time
import struct

HOST = "127.0.0.1"  
#PORT = 65432  # Port to listen on (non-privileged ports are > 1023)

def initConnection(side):
    ip = requests.get('https://api.ipify.org', verify=False).content.decode('utf8')
    #print(f'My IP address is: {ip}')
    if side == "slave":
        print("I'm slave")
        PORT = tcp_ports['slave']
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
                        ts = time.time()
                        start = ts + 0.2 
                        delay = start - time.time()
                        # print(start)
                        print(f'delay sending for {round(delay*1000,0)}ms')
                        conn.sendall(struct.pack('d',ts))
                        return "connected"
                    if not data:
                        break
    if side == "master":
        print("I'm master")
        PORT = tcp_ports['slave']
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
            tcp.connect((HOST, PORT))
            tcp.sendall(b"readyip"+str.encode(ip))
            data = tcp.recv(1024)
            if data.split(b'ip')[0] == b'g2g':
                opponent = data.split(b'ip')[1].decode('utf-8')
                print("Ready for Netlink!")
                print(f'Opponent IP: {opponent}')
                ts = tcp.recv(1024)
                st = struct.unpack('d',ts)[0]
                delay = st+0.2-time.time()
                start = delay + time.time()
                print(start)
                print(delay)
                return "connected"
                
    else:
        return "error"

                    
    
print(initConnection(sys.argv[1]))
