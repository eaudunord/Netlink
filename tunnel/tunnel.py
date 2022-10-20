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
import errno
import select
com_port = None
logger = logging.getLogger('dreampi')

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

updater()

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

    time_digit_heard = None
    while True:

        now = datetime.now()

        if mode == "LISTENING":
            modem.update()
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
                        if client == "direct_dial":
                            mode = "NETLINK ANSWERING"
                        else:
                            mode = "ANSWERING"
                        modem.stop_dial_tone()
                        time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "XBAND ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.query_modem("ATA", timeout=120, response = "CONNECT")
                xbandServer(modem)
                mode = "LISTENING"
                modem.connect()
                modem.start_dial_tone()
        elif mode == "NETLINK ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.connect_netlink(speed=57600,timeout=0.01,rtscts=True) #non-blocking version
                try:
                    modem.query_modem(b'AT%E0')
                    modem.query_modem(b"AT\N3\V1%C0")
                    modem.query_modem(b'AT+MS=V32b,1,14400,14400,14400,14400')
                    modem.query_modem("ATA", timeout=120, response = "CONNECT")
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

def xbandServer(modem):
    modem._serial.timeout = 0.1
    logger.info("connecting to retrocomputing.network")
    s = socket.socket()
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.setblocking(False)
    s.settimeout(15)
    s.connect(("xbserver.retrocomputing.network", 56969))
    hwid = b"0000000000000000"
    sdata = b"///////PI-" + hwid + b"\x0a"
    sentid = 0
    logger.info("connected")
    while True:
        try:
            ready = select.select([s], [], [],0)
            if ready[0]:
                data = s.recv(1024)
            if sentid == 0:
                s.send(sdata)
                sentid = 1
            if data:
                modem._serial.write(data)
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
                logger.info("CD still not asserted after 2 sec - xband hung up")
                for i in range(3):
                    modem._serial.write(b'+')
                    time.sleep(0.2)
                time.sleep(4)
                modem.send_command('ATH0')
                s.close()
                logger.info("Xband disconnected. Back to listening")
                return
        if modem._serial.in_waiting:
            data2 = modem._serial.read(1024)
        if data2:
            if sentid == 1:
                s.send(data2) #catch errors here pls

    

if __name__ == "__main__":
    process()

