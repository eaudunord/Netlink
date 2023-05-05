#xband_version=202304120907
import sys

if __name__ == "__main__":
    print("This script should not be run on its own")
    sys.exit()

import socket
import time
from datetime import datetime
import logging
import select
import os
import requests
import subprocess
import errno

osName = os.name
if osName == 'posix':
    logger = logging.getLogger('dreampi')
else:
    logger = logging.getLogger('Xband')
logger.setLevel(logging.INFO)

opponent_port = 4000
opponent_id = "11"
sock_listen = None
my_ip = "127.0.0.1"
try:
    r = requests.get("http://myipv4.p1.opendns.com/get_my_ip")
    r.raise_for_status()
    my_ip = r.json()['ip']
except requests.exceptions.HTTPError:
    logger.info("Couldn't get WAN IP")
    my_ip = "127.0.0.1"

if osName == 'posix': # should work on linux and Mac for USB modem, but untested.
    femtoSipPath = "/home/pi/dreampi/femtosip"
else:
    femtoSipPath = os.path.realpath('./')+"/femtosip"

def openXband():
    PORT = 65433
    global sock_listen
    sock_listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_listen.setblocking(0)
    sock_listen.bind(('', PORT))
    sock_listen.listen(5)
    logger.info("listening for xband call")

def closeXband():
    global sock_listen
    try:
        sock_listen.close()
    except:
        pass



def xbandInit():
    if os.path.exists(femtoSipPath) == False:
        try:
            os.makedirs(femtoSipPath)
            r = requests.get("https://raw.githubusercontent.com/eaudunord/femtosip/master/femtosip.py")
            r.raise_for_status()
            with open(femtoSipPath+"/femtosip.py",'wb') as f:
                text = r.content.decode('ascii','ignore').encode()
                f.write(text)
            logger.info('fetched femtosip')
            r = requests.get("https://github.com/astoeckel/femtosip/raw/master/LICENSE")
            r.raise_for_status()
            with open(femtoSipPath+"/LICENSE",'wb') as f:
                f.write(r.content)
            logger.info('fetched LICENSE')
            with open(femtoSipPath+"/__init__.py",'wb') as f:
                pass
        except requests.exceptions.HTTPError:
            logger.info("unable to fetch femtosip")
            return "dropped"
        except OSError:
            logger.info("error creating femtosip directory")
    else:
        global sip_ring
        import femtosip.femtosip as sip_ring

def xbandListen(modem):
    global sock_listen
    ready = select.select([sock_listen], [], [],0)
    if ready[0]:
        logger.info("incoming xband call")
        conn, addr = sock_listen.accept()
        opponent = addr[0]
        callTime = time.time()
        while True:
            ready = select.select([conn], [], [],0)
            if ready[0]:
                data = conn.recv(1024)
                if data == b"RESET":
                    modem.stop_dial_tone()
                    modem.connect_netlink(speed=57600,timeout=0.05,rtscts=True)
                    modem.query_modem(b'AT%E0')
                    modem.query_modem(b"AT\V1%C0")
                    modem.query_modem(b'AT+MS=V22b')
                    conn.sendall(b'ACK RESET')
                    # time.sleep(2)
                elif data == b"RING":
                    logger.info("RING")
                    # time.sleep(4)
                    conn.sendall(b'ANSWERING')
                    time.sleep(6)
                    logger.info('Answering')
                    modem.query_modem("ATX1D", timeout=120, response = "CONNECT")
                    logger.info("CONNECTED")
                elif data == b"PING":
                    conn.sendall(b'ACK PING')
                    modem._serial.timeout=None
                    modem._serial.write(b'\xff')
                    while True:
                        char = modem._serial.read(1) #read through the buffer and skip all 0xff
                        if char == b'\xff':
                            continue
                        elif char == b'\x01':
                            # modem._serial.write(b'\x01')
                            conn.sendall(b'RESPONSE')
                            logger.info('got a response')
                            break
                    if modem._serial.cd: #if we stayed connected
                        continue
                        
                    elif not modem._serial.cd: #if we dropped the call
                        logger.info("Xband Disconnected")
                        # mode = "LISTENING"
                        modem.connect()
                        modem.start_dial_tone()
                        return ("dropped","")
                    
                elif data == b'RESPONSE':
                    modem._serial.write(b'\x01')
                    if modem._serial.cd:
                        return ("connected",opponent)
                if time.time() - callTime > 120:
                    break
    return ("nothing","")
                    
def ringPhone(oppIP,modem):
    import femtosip.femtosip as sip_ring
    opponent = oppIP
    PORT = 65433
    sock_send = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_send.settimeout(15)
    logger.info("Calling opponent")
    # time.sleep(8)
    
    # sip = femtosip.SIP(user, password, gateway, port, display_name)
    # sip.call(call, delay)

    try:
        sock_send.connect((opponent, PORT))
        sock_send.sendall(b"RESET")
        sentCall = time.time()
        while True:
            ready = select.select([sock_send], [], [],0)
            if ready[0]:
                data = sock_send.recv(1024)
                if data == b'ACK RESET':
                    sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,protocol="udp")
                    sip.call(opponent_id,3)
                    sock_send.sendall(b'RING')
                elif data == b'ANSWERING':
                    logger.info("Answering")
                    modem.query_modem("ATA", timeout=120, response = "CONNECT")
                    logger.info("CONNECTED")
                    sock_send.sendall(b'PING')

                elif data == b"ACK PING":
                    modem._serial.timeout=None
                    modem._serial.write(b'\xff')
                    while True:
                        char = modem._serial.read(1) #read through the buffer and skip all 0xff
                        if char == b'\xff':
                            continue
                        elif char == b'\x01':
                            # modem._serial.write(b'\x01')
                            logger.info("got a response")
                            sock_send.sendall(b'RESPONSE')
                            break
                    if modem._serial.cd: #if we stayed connected
                        continue
                        
                    elif not modem._serial.cd: #if we dropped the call
                        return "hangup"

                elif data == b'RESPONSE':
                    modem._serial.write(b'\x01')
                    return opponent
            if time.time() - sentCall > 90:
                logger.info("opponent tunnel not responding")
                return "hangup"


    except socket.error:
        logger.info("couldn't connect to opponent")
        return "hangup"
    
def getserial():
  # Extract serial from cpuinfo file
  cpuserial = "0000000000000000"
  try:
    f = open('/proc/cpuinfo','r')
    for line in f:
      if line[0:6]=='Serial':
        cpuserial = line[10:26]
    f.close()
  except:
    cpuserial = "ERROR000000000"

  return cpuserial
    
def xbandServer(modem):
    modem._serial.timeout = 1
    logger.info("connecting to retrocomputing.network")
    s = socket.socket()
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.setblocking(False)
    s.settimeout(15)
    s.connect(("xbserver.retrocomputing.network", 56969))
    # cpu = subprocess.check_output(["wmic","cpu","get","ProcessorId","/format:csv"]).strip().split(b",")[-1]
    hwid = getserial().encode()
    sdata = b"///////PI-" + hwid + b"\x0a"
    sentid = 0
    logger.info("connected")
    while True:
        try:
            ready = select.select([s], [], [],0.3)
            if ready[0]:
                data = s.recv(1024)
                # print(data)
                modem._serial.write(data)
            if sentid == 0:
                s.send(sdata)
                sentid = 1
        except socket.error as e:
            err = e.args[0]
            if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                time.sleep(0.1)
            else:
                logger.warn("tcp connection dropped")
                break
        if not modem._serial.cd:
            logger.info("1: CD is not asserted")
            time.sleep(2.0)
            if not modem._serial.cd:
                logger.info("CD still not asserted after 2 sec - xband hung up")
                break
        if sentid == 1:        
            if modem._serial.in_waiting:
                line = b""
                while True:
                    data2 = modem._serial.read(1)
                    line += data2
                    if b"\x10\x03" in line:
                        # print(line)
                        s.send(line)
                        break
                    if not modem._serial.cd:
                        logger.info("2: CD is not asserted")
                        time.sleep(2.0)
                        if not modem._serial.cd:
                            logger.info("CD still not asserted after 2 sec - xband hung up")
                            break
    s.close()
    logger.info("Xband disconnected. Back to listening")
    return  
