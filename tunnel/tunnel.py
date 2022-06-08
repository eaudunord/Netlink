import netlink
from modemClass import Modem
import sys
from datetime import datetime
import logging
import time
logging.basicConfig(level=logging.INFO)
import serial

logger = logging.getLogger('dreampi')
com_port = sys.argv[1]
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
                logger.info("diconnecting serial port")
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

