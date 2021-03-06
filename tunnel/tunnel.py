import netlink
from modemClass import Modem
import sys
from datetime import datetime
import logging
import time
logging.basicConfig(level=logging.INFO)
import serial
com_port = None
logger = logging.getLogger('dreampi')

def com_scanner():
    global com_port
    speed = 115200
    for i in range(1,25): # this should be a big enough range. USB com ports usually end up in the teens.
        com_port = "COM%s" % i
        try:
            modem = Modem(com_port, speed,send_dial_tone=False)
            modem.connect_netlink()
            #print("potential modem found at %s" % com)
            query_modem(modem,"AT",timeout = 1) # potential modem. Other devices respond to AT, so not definitive.
            query_modem(modem,"AT+FCLASS=8",timeout = 1) # if potential modem, find out if it's our voice modem
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

def query_modem(modem, command, timeout=3):
              
        final_command = "%s\r\n" % command
        modem._serial.write(final_command)
        print(final_command)

        start = time.time()

        line = ""
        while True:
            new_data = modem._serial.readline().strip()

            if not new_data:
                if time.time() - start < timeout:
                    continue
                raise IOError()

            line = line + new_data
            
            if "OK" in line:
                return  # Valid response

try:
    com_port = sys.argv[1]
except IndexError:
    com_scanner()
    if com_port:
        print("Modem found at %s" % com_port)
    else:
        print("No modem found")
        sys.exit()


device_and_speed = [com_port,115200]
modem = Modem(device_and_speed[0], device_and_speed[1])


def do_netlink(side,dial_string):
    # ser = serial.Serial(device_and_speed[0], device_and_speed[1], timeout=0.02)
    state, opponent  = netlink.netlink_setup(device_and_speed,side,dial_string)
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
            char = modem._serial.read(1).strip()
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
                do_netlink(side,dial_string)
                logger.info("Netlink Disconnected")
                time.sleep(5)
                mode = "LISTENING"
                modem.connect()
                modem.start_dial_tone()

if __name__ == "__main__":
    process()

