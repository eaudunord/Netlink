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
    modem.reset()
    modem.send_command('AT&D0&Q6&S1E0&C1W2+MS=10s7=90\NX3DT0')
    modem.disconnect()

def send_data():
    ser = serial.Serial(device_and_speed[0], device_and_speed[1], timeout=0.02)
    for i in range(100):
        payload = str(time.time())
        ser.write(payload)

if __name__ == "__main__":
    dial_out()
    send_data()
