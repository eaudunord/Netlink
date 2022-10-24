#tunnel_version=1663983944.323452
import sys
import os
from datetime import datetime
import logging
import time
logging.basicConfig(level=logging.INFO)
import serial
import requests
import platform
import socket
import threading
import errno
import select
from xband_config import my_ip
from xband_config import opponent_ip
from xband_config import cpu_id_spoof
from xband_config import opponent_port
from xband_config import opponent_id
from xband_config import local_port
import sip_ring
com_port = None
logger = logging.getLogger('tunnel')

xbandnums = ["18002071194","19209492263","0120717360","0355703001"]

def updater():
    base_script_url = "https://raw.githubusercontent.com/eaudunord/Netlink/latest/tunnel/"
    checkScripts = ['modemClass.py','tunnel.py','netlink.py']
    restartFlag = False
    for script in checkScripts:
        url = base_script_url+script
        try:
            r=requests.get(url, stream = True)
            r.raise_for_status()
            for line in r.iter_lines():
                if b'_version' in line: 
                    upstream_version = str(line.decode().split('version=')[1]).strip()
                    break
            with open(script,'rb') as f:
                for line in f:
                    if b'_version' in line:
                        local_version = str(line.decode().split('version=')[1]).strip()
                        break
            if upstream_version == local_version:
                print('%s Up To Date' % script)
            else:
                optIn = "no"
                pythonVer = platform.python_version_tuple()[0]
                if pythonVer == '2':
                    optIn = raw_input('Update for %s available. Press enter to download or type no to skip >>' % script)
                else:
                    optIn = input('Update for %s available. Press enter to download or type no to skip >>' % script)
                if "no" in optIn.lower():
                    continue
                #make a handler for a bad request so bad data doesn't overwrite our local file
                r = requests.get(url)
                r.raise_for_status()
                with open(script,'wb') as f:
                    f.write(r.content)
                print('%s Updated' % script)
                if script == "tunnel.py":
                    restartFlag = True
            
        except requests.exceptions.HTTPError:
            logger.info("Couldn't check updates for: %s" % script)
            continue
    if restartFlag:
        print('Main script updated. Please restart the tunnel')
        sys.exit()

# updater()

import netlink
from modemClass import Modem


def com_scanner():
    global com_port
    speed = 115200
    for i in range(1,25): # this should be a big enough range. USB com ports usually end up in the teens.
        osName = os.name
        if osName == 'posix': # should work on linux and Mac for USB modem, but untested.
            com_port = "/dev/ttyACM%s" % i
        else:
            com_port = "COM%s" % i
        try:
            modem = Modem(com_port, speed,send_dial_tone=False)
            modem.connect_netlink()
            #print("potential modem found at %s" % com)
            modem.query_modem("AT",timeout = 1) # potential modem. Other devices respond to AT, so not definitive.
            modem.query_modem("AT+FCLASS=8",timeout = 1) # if potential modem, find out if it's our voice modem
            modem.reset()
            return com_port
        except serial.SerialException as e:
            message = str(e)
            # print(message)
            if "could not open port" in message:
                com_port = None
        except IOError as e:
            com_port = None
        finally:
            modem.disconnect()

try:
    com_port = sys.argv[1] #script can be started with com port as an argument. If it isn't, we can scan for the modem.
except IndexError:
    com_scanner()
    if com_port:
        print("Modem found at %s" % com_port)
    else:
        print("No modem found")
        sys.exit()


device_and_speed = [com_port,115200]
modem = Modem(device_and_speed[0], device_and_speed[1])


def do_netlink(side,dial_string,modem):
    # ser = serial.Serial(device_and_speed[0], device_and_speed[1], timeout=0.02)
    state, opponent  = netlink.netlink_setup(side,dial_string,modem)
    if state == "failed":
        for i in range(3):
            modem._serial.write(b'+')
            time.sleep(0.2)
        time.sleep(4)
        modem.send_command('ATH0')
        return
    netlink.netlink_exchange(side,state,opponent)


def process():
    mode = "LISTENING"

    modem.connect()
    modem.start_dial_tone()

    PORT = 65433
    sock_listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_listen.settimeout(120)
    sock_listen.bind(('', PORT))
    sock_listen.listen(5)

    time_digit_heard = None

    print(mode)
    while True:

        now = datetime.now()

        if mode == "LISTENING":
            modem.update()
            
            ready = select.select([sock_listen], [], [],0)
            if ready[0]:
                print(datetime.now(), "incoming xband call")
                conn, addr = sock_listen.accept()
                opponent = addr[0]
                while True:
                    try:
                        data = conn.recv(1024)
                    except socket.error: #first try can return no payload
                        continue
                    if data == b"RING":
                        conn.sendall(b'OK')
                        modem.stop_dial_tone()
                        time_digit_heard = now
                        modem.connect_netlink(speed=57600,timeout=0.05,rtscts=True)
                        modem.query_modem(b'AT%E0')
                        modem.query_modem(b"AT\V1%C0")
                        modem.query_modem(b'AT+MS=V22b')
                        time.sleep(2)
                        modem.query_modem("ATX1D", timeout=120, response = "CONNECT")
                        print(datetime.now(),"connected")
                        do_netlink("waiting","000",modem)
                        logger.info("Xband Disconnected")
                        mode = "LISTENING"
                        modem.connect()
                        modem.start_dial_tone()
                        break



            char = modem._serial.read(1).strip().decode()
            if not char:
                continue

            if ord(char) == 16:
                # DLE character
                try:
                    parsed = netlink.digit_parser(modem)
                    if parsed == "nada":
                        pass
                    elif isinstance(parsed,dict):
                        client = parsed['client']
                        dial_string = parsed['dial_string']
                        side = parsed['side']


                        logger.info("Heard: %s" % dial_string)
                        if dial_string in xbandnums:
                            logger.info("Incoming call from Xband")
                            client = "xband"
                            mode = "XBAND ANSWERING"
                        if dial_string == "11111111111":
                            client = "xband"
                            mode = "NETLINK ANSWERING"
                            side = "calling"
                            print(datetime.now(), "Invoke ring function")
                            t1 = threading.Thread(target=ringPhone)
                            t1.start() #ring opponent's phone, but don't wait for function to finish before moving on.
                            # time.sleep(4)
                            print(datetime.now(), "Ring invoked")

                        if client == "direct_dial":
                            mode = "NETLINK ANSWERING"
                        if client == "ppp_internet":
                            mode = "ANSWERING"
                        modem.stop_dial_tone()
                        time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "XBAND ANSWERING":
            # print("xband answering")
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.query_modem("ATA", timeout=120, response = "CONNECT")
                xbandServer(modem)
                mode = "LISTENING"
                modem.connect()
                modem.start_dial_tone()
        elif mode == "NETLINK ANSWERING":
            time_digit_heard = None
            try:
                if client == "xband":
                    modem.answer_xband()
                else:
                    modem.answer_netlink() #non-blocking version
                mode = "NETLINK_CONNECTED"
            except IOError:
                modem.connect()
                mode = "LISTENING"
                modem.start_dial_tone()


        elif mode == "CONNECTED":
            modem.connect()
            modem.send_escape()
            modem.start_dial_tone()
            mode = "LISTENING"

            
        elif mode == "NETLINK_CONNECTED":
            do_netlink(side,dial_string,modem)
            logger.info("Netlink Disconnected")
            # time.sleep(5)
            mode = "LISTENING"
            modem.connect()
            modem.start_dial_tone()
        # print(mode)

def xbandServer(modem):
    modem._serial.timeout = 1
    logger.info("connecting to retrocomputing.network")
    s = socket.socket()
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.setblocking(False)
    s.settimeout(15)
    s.connect(("xbserver.retrocomputing.network", 56969))
    hwid = cpu_id_spoof
    sdata = b"///////PI-" + hwid + b"\x0a"
    sentid = 0
    logger.info("connected")
    while True:
        try:
            ready = select.select([s], [], [],0)
            if ready[0]:
                data = s.recv(1024)
                print(data)
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
            logger.info("CD is not asserted")
            time.sleep(2.0)
            if not modem._serial.cd:
                logger.info(datetime.now(),"CD still not asserted after 2 sec - xband hung up")
                line = b""
                while True:
                    new = modem._serial.read(modem._serial.in_waiting)
                    line+=new
                    if b"NO CARRIER" in line:
                        print(datetime.now(),"NO CARRIER")
                    break
                break
        if sentid == 1:        
            if modem._serial.in_waiting:
                line = b""
                while True:
                    data2 = modem._serial.read(1)
                    line += data2
                    if b"\x10\x03" in line:
                        print(line)
                        s.send(line) #catch errors here pls
                        break
    
    for i in range(3):
        modem._serial.write(b'+')
        time.sleep(0.2)
    time.sleep(4)
    modem.send_command('ATH0')
    s.close()
    logger.info("Xband disconnected. Back to listening")
    return

def ringPhone():
    opponent = opponent_ip
    PORT = 65433
    sock_send = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_send.settimeout(15)
    print(datetime.now(), "Calling opponent")
    # time.sleep(8)
    sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,local_port=local_port)
    sip.call(opponent_id,3)
    # sip = femtosip.SIP(user, password, gateway, port, display_name)
    # sip.call(call, delay)

    try:
        sock_send.connect((opponent, PORT))
        sock_send.sendall(b"RING")
        ready = select.select([sock_send], [], [])
        if ready[0]:
            data = sock_send.recv(1024)
            if data == b'OK':
                return opponent

    except socket.error:
        return "error"
    

if __name__ == "__main__":
    process()

