# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""

import socket
from ports_def import tcp_ports
from ports_def import udp_ports
import sys
import requests
import struct
import time
import threading
import serial
from datetime import datetime
from modemClass import Modem

side = ""
com_port = sys.argv[1]
device_and_speed = [com_port,57600]
opponent = socket.gethostbyname(socket.gethostname())
data = []
HOST = socket.gethostbyname(socket.gethostname())
tcpPort = tcp_ports['slave']

#PORT = 65432  # Port to listen on (non-privileged ports are > 1023)
state = "disconnected"
jitterBuff = 0.02
poll_rate = 0.01
sync_delay = 0
start = 0
try:
    opponent = sys.argv[2]
except:
    pass

# with socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM) as udp:
#     udp.bind((HOST, udpPort))

def initConnection(ms):
    
    global opponent
    global start
    ip = requests.get('https://api.ipify.org').content.decode('utf8')
    #print(f'My IP address is: {ip}')
    if ms == "slave":
        print("I'm slave")
        PORT = tcpPort
        #udpPort = udp_ports['slave']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind((HOST, PORT))
        tcp.listen(5)
        conn, addr = tcp.accept()
        while True:
            data = conn.recv(1024)
            if data.split(b'ip')[0] == b'ready':
                conn.sendall(b'g2gip'+(ip))
                print("Sending Ring")
                ser.write("RING\r\n")
                ser.write("CONNECT\r\n")
                # opponent = data.split(b'ip')[1].decode('utf-8')
                print("Ready for Netlink!")
                # print('Opponent IP: %s'% opponent)
                ts = time.time()
                start = ts + 0.2 
                conn.sendall(struct.pack('d',ts))
                return "connected"
            if not data:
                break
    if ms == "master":
        print("I'm master")
        PORT = tcpPort
        #udpPort = udp_ports['master']
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.connect((opponent, PORT))
        tcp.sendall(b"readyip"+(ip))
        data = tcp.recv(1024)
        if data.split(b'ip')[0] == b'g2g':
            # opponent = data.split(b'ip')[1].decode('utf-8')
            print("Ready for Netlink!")
            # print('Opponent IP: %s'% opponent)
            ts = tcp.recv(1024)
            st = struct.unpack('d',ts)[0]
            delay = st+0.2-time.time()
            start = delay + time.time()
            return "connected"
                
    else:
        return "error"



def listener():
    while(state == "connected"):
        try:
            # print("test")
            # time.sleep(jitterBuff)
            packet = udp.recvfrom(1024)
            message = packet[0]
            payload = message.split(b'sequenceno')[0]
            raw_sequence = message.split(b'sequenceno')[1]
            sequence = struct.unpack('d',raw_sequence)[0]
            if len(payload) > 0:
                print(payload)
            # if len(payload) == 0:
                # payload = "emptynull"
            data.append({'ts':sequence,'data':payload})
            
        except KeyboardInterrupt:
            print("Error thread 1")
            sys.exit()
                
def printer():
    global com_port
    global state
    first_run = True
    print("I'm the printer")
    while(state == "connected"):
        try:
            read = data.pop(0)
            ts = read['ts']
            toSend = read['data']
            # if toSend == "emptynull":
            #     time.sleep(poll_rate)
            #     continue
            if first_run == True:
                # time.sleep(jitterBuff)
                first_run = False
            #print(toSend)
            latency = round(((time.time() - ts)*1000),0)
            if len(toSend) >0:
                print('latency: %sms' % latency)
                print(toSend)
                    
            # time.sleep(poll_rate)
            ser.write(toSend)
        except:
            #time.sleep(.01)
            continue
            
def sender():
    global state
    print("sending")
    first_run = True
    if side == "slave":
        oppPort = udp_ports['master']
    if side == 'master':
        oppPort = udp_ports['slave']
    while(state == "connected"):
        # if first_run == True:
        #     ser.read(1024)
        #     first_run = False
        raw_input = ser.read(1024)
        if len(raw_input) == 0:
            continue
        if "NO CARRIER" in raw_input:
            state = "disconnected"
            break
        # delimiter = str.encode("sequenceno",'ANSI')
        delimiter = "sequenceno"
        try:
            # payload = str.encode(raw_input,'ANSI')
            payload = raw_input
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (opponent,oppPort))
            
            # time.sleep(.02)
            #raw_input = input(">> ")
        except KeyboardInterrupt:
            sys.exit()
        except ConnectionResetError:
            continue
            
def process():
    #This is nearly identical to the dreampi connection script except for mode == "CONNECTED"
    #This is where you can use digit recognition to branch out to Netlink
    global side
    # killer = GracefulKiller()

    dial_tone_enabled = "--disable-dial-tone" not in sys.argv

    # Make sure pppd isn't running
    # with open(os.devnull, 'wb') as devnull:
    #     subprocess.call(["sudo", "killall", "pppd"], stderr=devnull)

    # device_and_speed, internet_connected = None, False

    # # Startup checks, make sure that we don't do anything until
    # # we have a modem and internet connection
    # while True:
    #     print("Detecting connection and modem...")
    #     internet_connected = check_internet_connection()
    #     device_and_speed = detect_device_and_speed()

    #     if internet_connected and device_and_speed:
    #         print("Internet connected and device found!")
    #         break

    #     elif not internet_connected:
    #         print("Unable to detect an internet connection. Waiting...")
    #     elif not device_and_speed:
    #         print("Unable to find a modem device. Waiting...")

    #     time.sleep(5)

    modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
    # dreamcast_ip = autoconfigure_ppp(modem.device_name, modem.device_speed)

    # Get a port forwarding object, now that we know the DC IP.
    # port_forwarding = PortForwarding(dreamcast_ip, logger)

    # Disabled until we can figure out a faster way of doing this.. it takes a minute
    # on my router which is way too long to wait for the DreamPi to boot
    # port_forwarding.forward_all()

    mode = "LISTENING"

    modem.connect()
    if dial_tone_enabled:
        modem.start_dial_tone()

    time_digit_heard = None

    # dcnow = DreamcastNowService()

    while True:
        # if killer.kill_now:
        #     break

        now = datetime.now()

        if mode == "LISTENING":
            modem.update()
            char = modem._serial.read(1).strip()
            if not char:
                continue

            if ord(char) == 16:
                # DLE character
                try:
                    char = modem._serial.read(1)
                    digit = int(char)
                    print("Heard: %s" % digit)

                    mode = "ANSWERING"
                    modem.stop_dial_tone()
                    time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                ts = time.time()
                modem.answer()
                time_to_answer = time.time() - ts
                print('Time to answer: %s' % time_to_answer)
                # modem.disconnect()
                ts = time.time()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "CONNECTED":
            # dcnow.go_online(dreamcast_ip)

            # We start watching /var/log/messages for the hang up message
            # for line in sh.tail("-f", "/var/log/messages", "-n", "1", _iter=True):
            #     if "Modem hangup" in line:
            #         print("Detected modem hang up, going back to listening")
            #         time.sleep(5)  # Give the hangup some time
            #         break

            # dcnow.go_offline()
            if digit == 0:
                
                side = "slave"
                return
            if digit == 7:
                side = "master"
                return
            # firstRun = True
            # log = ""
            # while True:
            #     try:
            #         if firstRun == True:
            #             time.sleep(2)
            #             raw = bytes(reader.read(1024))
            #             firstRun = False
            #             # log = raw
            #         else:
            #             raw = bytes(reader.read(1))
            #             log += raw
            #     except KeyboardInterrupt:
            #         print(bytes(log))
            #         sys.exit()
                 
            #     interval = (time.time()-ts)*1000
            #     # print(interval)
            #     ts = time.time()
            #     if len(raw) > 0:
            #         print(raw)
            #         print(interval)
process()
print("process says I'm %s" % side)              
t1 = threading.Thread(target=listener)
# t1.setDaemon(True)
t2 = threading.Thread(target=printer)
# t2.setDaemon(True)
t3 = threading.Thread(target=sender)
# t3.setDaemon(True)
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.bind((HOST, udp_ports[side]))
ser = serial.Serial(com_port, device_and_speed[1], timeout=poll_rate)
state = initConnection(side)
print(state)
sync_delay = start-time.time()
# time.sleep(sync_delay) 
                
if state == "connected":
    t1.start()
    t2.start()
    t3.start()
    # t1.join()
    # t2.join()
    # t3.join()
        


