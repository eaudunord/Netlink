# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
if __name__ == "__main__":
    import socket
    import sys
    import time
    import serial
    from datetime import datetime
    from modemClass import Modem
    com_port = sys.argv[1]
    device_and_speed = [com_port,57600]
    import logging
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger('dreampi')
    # opponent = socket.gethostbyname(socket.gethostname())
import struct
import threading

side = ""


# data = []
HOST = socket.gethostbyname(socket.gethostname())


state = "netlink_disconnected"
jitterBuff = 0.0
poll_rate = 0.02
sync_delay = 0
start = 0
try:
    opponent = sys.argv[2]
except:
    pass

def initConnection(ms):
    
    global opponent
    global start
    if ms == "slave":
        logger.info("I'm slave")
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.bind((HOST, PORT))
        tcp.listen(5)
        conn, addr = tcp.accept()
        opponent = addr[0]
        while True:
            data = conn.recv(1024)
            if data.split(b'ip')[0] == b'ready':
                conn.sendall(b'g2gip')
                logger.info("Sending Ring")
                ser.write("RING\r\n")
                ser.write("CONNECT\r\n")
                logger.info("Ready for Netlink!")
                ts = time.time()
                start = ts + 0.3 
                conn.sendall(struct.pack('d',ts))
                return "connected"
            if not data:
                break
    if ms == "master":
        logger.info("I'm master")
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.connect((opponent, PORT))
        tcp.sendall(b"readyip")
        data = tcp.recv(1024)
        if data.split(b'ip')[0] == b'g2g':
            # opponent = data.split(b'ip')[1].decode('utf-8')
            logger.info("Ready for Netlink!")
            # logger.info('Opponent IP: %s'% opponent)
            ts = tcp.recv(1024)
            st = struct.unpack('d',ts)[0]
            delay = st+0.2-time.time()
            start = delay + time.time()
            return "connected"
                
    else:
        return "error"



def listener():
    data = []
    while(state == "connected"):
        try:
            packet = udp.recvfrom(1024)
            message = packet[0]
            payload = message.split(b'sequenceno')[0]
            raw_sequence = message.split(b'sequenceno')[1]
            sequence = struct.unpack('d',raw_sequence)[0]
            data.append({'ts':sequence,'data':payload})
            if len(payload) > 0:
                logger.info(payload)
        except KeyboardInterrupt:
            logger.info("Error thread 1")
            sys.exit()
                
def printer():
    global com_port
    global state
    logger.info("I'm the printer")
    while(state == "connected"):
        try:
            read = data.pop(0)
            ts = read['ts']
            toSend = read['data']
            latency = round(((time.time() - ts)*1000),0)
            if len(toSend) >0:
                logger.info('latency: %sms' % latency)
                logger.info(toSend)
            ser.write(toSend)
        except:
            continue
            
def sender():
    global state
    logger.info("sending")
    first_run = True
    if side == "slave":
        oppPort = 20002
    if side == 'master':
        oppPort = 20001
    while(state == "connected"):
        if first_run == True:
            ser.read(1024)
            first_run = False
        raw_input = ser.read(1024)
        if "NO CARRIER" in raw_input:
            state = "netlink_disconnected"
            break
        delimiter = "sequenceno"
        try:
            payload = raw_input
            ts = time.time()
            udp.sendto((payload+delimiter+struct.pack('d',ts)), (opponent,oppPort))
        except KeyboardInterrupt:
            sys.exit()
            
def netlink_process():
    #This is nearly identical to the dreampi connection script except for mode == "CONNECTED"
    #This is where you can use digit recognition to branch out to Netlink
    global side

    dial_tone_enabled = "--disable-dial-tone" not in sys.argv

    modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)

    mode = "LISTENING"

    modem.connect()
    if dial_tone_enabled:
        modem.start_dial_tone()

    time_digit_heard = None

    while True:

        now = datetime.now()

        if mode == "LISTENING":
            global char
            modem.update()
            char = modem._serial.read(1).strip()
            if not char:
                continue

            if ord(char) == 16:
                # DLE character
                try:
                    char = modem._serial.read(1)
                    digit = int(char)
                    logger.info("Heard: %s" % digit)

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
                logger.info('Time to answer: %s' % time_to_answer)
                ts = time.time()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "CONNECTED":
            
            if digit == 0:
                
                side = "slave"
                return
            if digit == 7:
                side = "master"
                return

def digit_parser(char,modem):
    if ord(char) == 16:
            # DLE character
            try:
                char = modem._serial.read(1)
                digit = int(char)
                logger.info("Heard: %s", digit)

                mode = "ANSWERING"
                modem.stop_dial_tone()
                time_digit_heard = now
            except (TypeError, ValueError):
                pass

if __name__ == "__main__":
    netlink_process()
    logger.info("process says I'm %s" % side)              


def netlink_exchange():
    global state
    global ser
    global udp
    ser = serial.Serial(com_port, device_and_speed[1], timeout=poll_rate)
    state = initConnection(side)
    time.sleep(0.2) 
                    
    if state == "connected":
        t1 = threading.Thread(target=listener)
        t2 = threading.Thread(target=printer)
        t3 = threading.Thread(target=sender)
        if side == "slave":
            Port = 20001
        if side == 'master':
            Port = 20002
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind((HOST, Port))
        t1.start()
        t2.start()
        t3.start()
    
if __name__ == "__main__":
    netlink_exchange()
        


