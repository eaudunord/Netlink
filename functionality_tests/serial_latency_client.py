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

def dial_out():
    modem.connect_netlink()
    modem.send_escape()
    modem.send_escape()
    modem.send_command('ATH')
    modem.reset()
    modem.send_command('AT&D0&Q6&S1E0&C1W2+MS=10s7=90\NX1')
    time.sleep(3)
    modem.send_command('atdt555',ignore_responses=["OK"])
    while True:
        try:
            payload = str(time.time())
            modem._serial.write(payload)
            time.sleep(0.032)
        except KeyboardInterrupt:
            modem.send_escape()
            modem.send_escape()
            modem.send_command('ATH')
            modem.disconnect()
            return
    

if __name__ == "__main__":
    dial_out()
