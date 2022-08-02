import serial
from modemClass import Modem
import datetime
import time
com = None
def com_scanner():
    global com
    speed = 115200
    for i in range(1,25): # this should be a big enough range. USB com ports usually end up in the teens.
        com = "COM%s" % i
        try:
            modem = Modem(com, speed,send_dial_tone=False)
            modem.connect_netlink()
            #print("potential modem found at %s" % com)
            query_modem(modem,"AT",timeout = 1) # potential modem. Other devices respond to AT, so not definitive.
            query_modem(modem,"AT+FCLASS=8",timeout = 1) # if potential modem, find out if it's our voice modem
            modem.reset()
            return com
        except serial.SerialException as e:
            message = str(e)
            # print(message)
            if "could not open port" in message:
                com = None
        except IOError as e:
            com = None
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


com_scanner()
if com:
    print("Modem found at %s" % com)
else:
    print("No modem found")