# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""

import struct
import threading


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
    # dial_tone_enabled = "--disable-dial-tone" not in sys.argv
    # modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)

def digit_parser(modem):
    char = modem._serial.read(1)
    tel_digits = ['1', '2', '3', '4', '5', '6', '7', '8', '9']
    ip_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9','*']
    if char in tel_digits:
        return {'client':'ppp_internet','dial_string':char,'side':'na'}
    elif char == '0':
        return {'client':'direct_dial','dial_string':char,'side':'slave'}
    elif char == '#': #this isn't going to work because DLE precedes all digits dialed. Fix this.
        dial_string = ""
        while (True):
            char = modem._serial.read(1)
            if not char:
                continue
            if ord(char) == 16:
                try:
                    char = modem._serial.read(1)
                    if char == '#':
                        dial_string = dial_string.replace('*','.')
                        break
                    if char in ip_digits:
                        dial_string += char
                except (TypeError, ValueError):
                    pass
        return {'client':'direct_dial','dial_string':dial_string,'side':'master'}
    else:
        return "nada"



def netlink_listener():
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
            # global char
            modem.update()
            char = modem._serial.read(1).strip()
            if not char:
                continue

            if ord(char) == 16:
                # DLE character
                try:
                    parsed = digit_parser(modem)
                    if parsed == "nada":
                        pass
                    elif isinstance(parsed,dict):
                        client = parsed['client']
                        dial_string = parsed['dial_string']
                        side = parsed['side']


                        logger.info("Heard: %s" % dial_string)

                        mode = "ANSWERING"
                        modem.stop_dial_tone()
                        time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.answer()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "CONNECTED":
            
            if client == "direct_dial":
                netlink_process(side=side,dial_string=dial_string,device_and_speed=device_and_speed)
                mode = "LISTENING"
                modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
                modem.connect()
                if dial_tone_enabled:
                    modem.start_dial_tone()

def netlink_process(side="",dial_string="",device_and_speed=""):
    HOST = socket.gethostbyname(socket.gethostname())
    poll_rate = 0.02
    state = "netlink_disconnected"
    data = []
    global opponent

    def initConnection(ms,ser):
        global opponent
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
            opponent = dial_string
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
    def listener(udp):
        check = 0.00
        while(state == "connected"):
            try:
                packet = udp.recvfrom(1024)
                message = packet[0]
                payload = message.split(b'sequenceno')[0]
                raw_sequence = message.split(b'sequenceno')[1]
                sequence = struct.unpack('d',raw_sequence)[0]
                if sequence < check:
                    continue
                check = sequence
                data.append({'ts':sequence,'data':payload})
                if len(payload) > 0:
                    logger.info(payload)
            except KeyboardInterrupt:
                logger.info("Error thread 1")
                break
    def printer(ser):
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
    def sender(ser,udp):
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

    def netlink_exchange(device_and_speed):
        ser = serial.Serial(com_port, device_and_speed[1], timeout=poll_rate)
        state = initConnection(side,ser)
        time.sleep(0.2) 
                        
        if state == "connected":
            if side == "slave":
                Port = 20001
            if side == 'master':
                Port = 20002
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp.bind((HOST, Port))
            t1 = threading.Thread(target=listener,args=(udp))
            t2 = threading.Thread(target=printer, args=(ser))
            t3 = threading.Thread(target=sender, args=(ser,udp))
            t1.start()
            t2.start()
            t3.start()
    
    netlink_exchange(device_and_speed)

if __name__ == "__main__":
    netlink_listener()
