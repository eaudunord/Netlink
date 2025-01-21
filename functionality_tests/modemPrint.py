import os
import serial
from datetime import datetime
from datetime import timedelta
import time
import sys
device_and_speed = ['COM6',57600]

from modemClass import Modem

def process():
    # killer = GracefulKiller()

    dial_tone_enabled = "--disable-dial-tone" not in sys.argv

    # Make sure pppd isn't running
    # with open(os.devnull, 'wb') as devnull:
    #     subprocess.call(["sudo", "killall", "pppd"], stderr=devnull)

    # device_and_speed, internet_connected = None, False

    # # Startup checks, make sure that we don't do anything until
    # # we have a modem and internet connection
    # while True:
    #     print("Detecting connection and modem...")
    #     internet_connected = check_internet_connection()
    #     device_and_speed = detect_device_and_speed()

    #     if internet_connected and device_and_speed:
    #         print("Internet connected and device found!")
    #         break

    #     elif not internet_connected:
    #         print("Unable to detect an internet connection. Waiting...")
    #     elif not device_and_speed:
    #         print("Unable to find a modem device. Waiting...")

    #     time.sleep(5)

    modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
    # dreamcast_ip = autoconfigure_ppp(modem.device_name, modem.device_speed)

    # Get a port forwarding object, now that we know the DC IP.
    # port_forwarding = PortForwarding(dreamcast_ip, logger)

    # Disabled until we can figure out a faster way of doing this.. it takes a minute
    # on my router which is way too long to wait for the DreamPi to boot
    # port_forwarding.forward_all()

    mode = "LISTENING"

    modem.connect()
    if dial_tone_enabled:
        modem.start_dial_tone()

    time_digit_heard = None

    # dcnow = DreamcastNowService()

    while True:
        # if killer.kill_now:
        #     break

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
                    print("Heard: %s" % digit)

                    mode = "ANSWERING"
                    modem.stop_dial_tone()
                    time_digit_heard = now
                except (TypeError, ValueError):
                    pass
        elif mode == "ANSWERING":
            if (now - time_digit_heard).total_seconds() > 8.0:
                time_digit_heard = None
                ts = time.time()
                modem.answer()
                time_to_answer = time.time() - ts
                print('Time to answer: %s' % time_to_answer)
                # modem.disconnect()
                ts = time.time()
                modem.disconnect()
                mode = "CONNECTED"

        elif mode == "CONNECTED":
            # dcnow.go_online(dreamcast_ip)

            # We start watching /var/log/messages for the hang up message
            # for line in sh.tail("-f", "/var/log/messages", "-n", "1", _iter=True):
            #     if "Modem hangup" in line:
            #         print("Detected modem hang up, going back to listening")
            #         time.sleep(5)  # Give the hangup some time
            #         break

            # dcnow.go_offline()
            reader = serial.Serial(device_and_speed[0], device_and_speed[1],timeout=0.02)
            if digit == 0:
                print("Sending Ring")
                reader.write("RING\r\n")
                reader.write("CONNECT\r\n")
            firstRun = True
            log = ""
            while True:
                try:
                    if firstRun == True:
                        time.sleep(2)
                        raw = bytes(reader.read(1024))
                        firstRun = False
                        # log = raw
                    else:
                        raw = bytes(reader.read(1))
                        log += raw
                except KeyboardInterrupt:
                    print(bytes(log))
                    sys.exit()
                 
                interval = (time.time()-ts)*1000
                # print(interval)
                ts = time.time()
                if len(raw) > 0:
                    print(raw)
                    print(interval)


            # time.sleep(120)
            # mode = "LISTENING"
            # modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
            # modem.connect()
            # if dial_tone_enabled:
            #     modem.start_dial_tone()

    # Temporarily disabled, see above
    # port_forwarding.delete_all()
    # return 0
process()