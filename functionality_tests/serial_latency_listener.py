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


def do_netlink():
    state = "connected"
    logger.info("sending")
    first_run = False
    last = 0
    sequence = 0.0
    ser = serial.Serial(device_and_speed[0], device_and_speed[1], timeout=0.03)
    while(state != "netlink_disconnected"):
        
        if ser.in_waiting > 0:
            now = time.time()
            t_delta = round(((now - last)*1000),0)
            # logger.info("Serial Spacing: %s" % t_delta)
            # last = now
            if t_delta > 0.025 and t_delta < 0.038:
                time.sleep(0.015)
        # logger.info("%s bytes waiting to be read" % ser.in_waiting)
            if first_run == True:
                raw_input = ser.read(1024)
                first_run = False
                raw_input = ser.read(ser.in_waiting)
            else:
                raw_input = ser.read(ser.in_waiting)
                new_delta = round(((time.time() - last)*1000),0)
                logger.info("new spacing: %s" % new_delta)
                last = now
            if "NO CARRIER" in raw_input:
                logger.info("detected hangup")
                state = "netlink_disconnected"
                time.sleep(1)
                # udp.close()
                ser.flush()
                ser.close()
                logger.info("sender stopped")
                return
            delimiter = "sequenceno"
            try:
                ts = float(raw_input)
                latency = round((time.time()-ts)*1000,0)
                # logger.info("Receive Latency: %s" % latency)
            except (TypeError, ValueError):
                continue


def process():
    mode = "LISTENING"

    modem.connect()
    modem.send_escape()
    modem.send_escape()
    modem.send_command('ATH')
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
                    char = modem._serial.read(1)
                    digit = int(char)
                    logger.info("Heard: %s", digit)

                    mode = "ANSWERING"
                    modem.stop_dial_tone()
                    time_digit_heard = now
                except (TypeError, ValueError):
                    pass

        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                modem.lat_answer()
                modem.disconnect()
                mode = "CONNECTED"
                return

        # elif mode == "CONNECTED":
            
        #     do_netlink()
        #     logger.info("Netlink Disconnected")
        #     time.sleep(5)
        #     mode = "LISTENING"
        #     modem.connect()
        #     modem.start_dial_tone()

if __name__ == "__main__":
    process()
    do_netlink()

