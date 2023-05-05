#tunnel_version=202305030924
import sys
import os
from datetime import datetime
import logging
import time
logging.basicConfig(level=logging.INFO)
import serial
import requests
import platform
com_port = None
logger = logging.getLogger('Netlink')



def updater():
    base_script_url = "https://raw.githubusercontent.com/eaudunord/Netlink/latest/tunnel/"
    checkScripts = ['modemClass.py','tunnel.py','netlink.py','xband.py']
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
            local_script = os.path.realpath('./') + "/" +script
            if os.path.isfile(local_script) == False:
                local_version = None
            else:
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

if 'noUpdate' in sys.argv:
    print("updates disabled")
else:
    updater()

import netlink
from modemClass import Modem
import xband


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
    if 'com' not in com_port.lower():
        raise IndexError
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
    xbandnums = ["18002071194","19209492263","0120717360","0355703001"]
    
    xbandMatching = False
    xbandTimer = None
    xbandInit = False
    openXband = False

    mode = "LISTENING"

    modem.connect()
    modem.start_dial_tone()

    time_digit_heard = None
    saturn = True
    while True:

        now = datetime.now()

        if mode == "LISTENING":

            if xbandMatching == True:
                if xbandInit == False:
                    xband.xbandInit()
                    xbandInit = True
                if time.time() - xbandTimer > 900:
                    xbandMatching = False
                    xband.closeXband()
                    openXband = False
                    continue
                if openXband == False:
                    xband.openXband()
                    openXband = True
                xbandResult,opponent = xband.xbandListen(modem)
                if xbandResult == "connected":
                    netlink.netlink_exchange("waiting","connected",opponent,ser=modem._serial)
                    logger.info("Xband Disconnected")
                    mode = "LISTENING"
                    modem.connect()
                    modem.start_dial_tone()
                    xbandMatching = False
                    xband.closeXband()
                    openXband = False

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

                        elif dial_string == "00":
                            side = "waiting"
                            client = "direct_dial"

                        elif dial_string[0:3] == "859":
                            try:
                                kddi_opponent = dial_string
                                kddi_lookup = "https://dial.redreamcast.net/?phoneNumber=%s" % kddi_opponent
                                response = requests.get(kddi_lookup)
                                response.raise_for_status()
                                ip = response.text
                                if len(ip) == 0:
                                    pass
                                else:
                                    dial_string = ip
                                    logger.info(dial_string)
                                    saturn = False
                                    side = "calling"
                                    client = "direct_dial"
                                    time.sleep(7)
                            except requests.exceptions.HTTPError:
                                pass

                        elif len(dial_string.split('*')) == 5 and dial_string.split('*')[-1] == "1":
                            oppIP = '.'.join(dial_string.split('*')[0:4])
                            client = "xband"
                            mode = "NETLINK ANSWERING"
                            side = "calling"
                        
                        if client == "direct_dial":
                            mode = "NETLINK ANSWERING"
                        elif client == "xband":
                            pass
                        else:
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
                xband.xbandServer(modem)
                mode = "LISTENING"
                modem.connect()
                modem.start_dial_tone()
                xbandMatching = True
                xbandTimer = time.time()

        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.answer()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "NETLINK ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                
                try:
                    if client == "xband":
                        modem.init_xband()
                        result = xband.ringPhone(oppIP,modem)
                        if result == "hangup":
                            mode = "LISTENING"
                            modem.connect()
                            modem.start_dial_tone()
                        else:
                            mode = "NETLINK_CONNECTED"
                    else:
                        modem.connect_netlink(speed=57600,timeout=0.01,rtscts = True) #non-blocking version
                        modem.query_modem(b"AT%E0\V1")
                        if saturn:
                            modem.query_modem(b'AT%C0\N3')
                            modem.query_modem(b'AT+MS=V32b,1,14400,14400,14400,14400')
                        modem.query_modem(b"ATA", timeout=120, response = "CONNECT")
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
            if client == "xband":
                netlink.netlink_exchange("calling","connected",oppIP,ser=modem._serial)
            else:
                do_netlink(side,dial_string,modem)
            logger.info("Netlink Disconnected")
            # time.sleep(5)
            mode = "LISTENING"
            modem.connect()
            modem.start_dial_tone()

if __name__ == "__main__":
    process()

