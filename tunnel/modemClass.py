#modemClass_version=202307212009
import os
import serial
from datetime import datetime
from datetime import timedelta
import time



class Modem(object):
    def __init__(self, device, speed, send_dial_tone=True):
        self._device, self._speed = device, speed
        self._serial = None
        self._sending_tone = False

        if send_dial_tone:
            self._dial_tone_wav = self._read_dial_tone()
        else:
            self._dial_tone_wav = None

        self._time_since_last_dial_tone = None
        self._dial_tone_counter = 0

    @property
    def device_speed(self):
        return self._speed

    @property
    def device_name(self):
        return self._device

    def _read_dial_tone(self):
        this_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
        dial_tone_wav = os.path.join(this_dir, "dial-tone.wav")

        with open(dial_tone_wav, "rb") as f:
            dial_tone = f.read()  # Read the entire wav file
            dial_tone = dial_tone[44:]  # Strip the header (44 bytes)

        return dial_tone

    def connect(self): #blocking
        if self._serial:
            self.disconnect()

        print("Opening serial interface to {}".format(self._device))
        self._serial = serial.Serial(
            self._device, self._speed, timeout=0
        )
    def connect_netlink(self,speed = 115200, timeout = 0.01, rtscts = False): #non-blocking
        if self._serial:
            self.disconnect()
        print("Opening serial interface to {}".format(self._device))
        self._serial = serial.Serial(
            self._device, speed, timeout=timeout, rtscts = rtscts
        )

    def disconnect(self):
        if self._serial and self._serial.isOpen():
            self._serial.flush() #added a flush, is data hanging on in the buffer?
            self._serial.close()
            self._serial = None
            # print("Serial interface terminated")

    def reset(self):
        while True:
            try:
                self.send_command("ATZ0",timeout=3)  # Send reset command
                time.sleep(1)
                self.send_command("AT&F0")
                self.send_command("ATE0W2")  # Don't echo our responses
                return
            except IOError:
                self.shake_it_off() # modem isn't responding. Try a harder reset

    def start_dial_tone(self):
        if not self._dial_tone_wav:
            return

        i = 0
        while i < 3:
            try:
                self.reset()
                self.send_command(b"AT+FCLASS=8")  # Enter voice mode
                self.send_command(b"AT+VLS=1")  # Go off-hook
                self.send_command(b"AT+VSM=1,8000")  # 8 bit unsigned PCM
                self.send_command(b"AT+VTX")  # Voice transmission mode
                print("<LISTENING>")
                break
            except IOError:
                time.sleep(0.5)
                i+=1
                pass

        self._sending_tone = True

        self._time_since_last_dial_tone = (
            datetime.now() - timedelta(seconds=100)
        )

        self._dial_tone_counter = 0

    def stop_dial_tone(self):
        if not self._sending_tone:
            return

        self._serial.write(("\0{}{}\r\n".format(chr(0x10), chr(0x03))).encode())
        self.send_escape()
        self.send_command("ATH0")  # Go on-hook
        self.reset()  # Reset the modem
        self._sending_tone = False

    def answer(self):
        self.reset()
        # When we send ATA we only want to look for CONNECT. Some modems respond OK then CONNECT
        # and that messes everything up
        self.send_command("ATA", ignore_responses=["OK"])
        #time.sleep(5)
        print("Call answered!")
        # logger.info(subprocess.check_output(["pon", "dreamcast"]))
        print("Connected")
    
    def query_modem(self, command, timeout=3, response = "OK"): #this function assumes we're being passed a non-blocking modem

        if isinstance(command, bytes):
            final_command = command + b'\r\n'
        else:
            final_command = ("%s\r\n" % command).encode()
        self._serial.write(final_command)
        print('Command: %s' % final_command.decode())

        start = time.time()

        line = b""
        while True:
            new_data = self._serial.readline().strip()

            if not new_data: #non-blocking modem will end up here when timeout reached, try until this function's timeout is reached.
                if time.time() - start < timeout:
                    continue
                raise IOError("There was a timeout while waiting for a response from the modem")

            line = line + new_data
            
            if response.encode() in line:
                if response != "OK":
                    print('Response: %s' % line.decode())
                return  # Valid response
         

    def send_command(self, command, timeout=60, ignore_responses=None):

        ignore_responses = ignore_responses or []  # Things to completely ignore

        VALID_RESPONSES = [b"OK", b"ERROR", b"CONNECT", b"VCON"]

        for ignore in ignore_responses:
            VALID_RESPONSES.remove(ignore.encode())

        if isinstance(command, bytes):
            final_command = command + b'\r\n'
        else:
            final_command = ("%s\r\n" % command).encode() 

        self._serial.write(final_command)
        print('Command: %s' % final_command.decode())

        start = time.time()
        line = b""
        while True:
            new_data = self._serial.readline().strip()

            if not new_data:
                if time.time() - start < timeout:
                    continue
                raise IOError("There was a timeout while waiting for a response from the modem")

            line = line + new_data
            for resp in VALID_RESPONSES:
                if resp in line:
                    if resp != b"OK":
                        print('Response: %s' % line.decode())
                        if resp == b"ERROR":
                            raise IOError("Command returned an error")

                    # logger.info(line[line.find(resp):])
                    return  # We are done


    def send_escape(self):
        time.sleep(1.0)
        self._serial.write(b"+++")
        time.sleep(1.0)

    def shake_it_off(self): #sometimes the modem gets stuck in data mode
        for i in range(3):
            self._serial.write(b'+')
            time.sleep(0.2)
        time.sleep(4)
        self.send_command('ATH0') #make sure we're on hook
        print("Shook it off")

    def update(self):
        now = datetime.now()
        if self._sending_tone:
            # Keep sending dial tone
            BUFFER_LENGTH = 1000
            TIME_BETWEEN_UPLOADS_MS = (1000.0 / 8000.0) * BUFFER_LENGTH

            milliseconds = (now - self._time_since_last_dial_tone).microseconds * 1000
            if not self._time_since_last_dial_tone or milliseconds >= TIME_BETWEEN_UPLOADS_MS:
                byte = self._dial_tone_wav[self._dial_tone_counter:self._dial_tone_counter+BUFFER_LENGTH]
                self._dial_tone_counter += BUFFER_LENGTH
                if self._dial_tone_counter >= len(self._dial_tone_wav):
                    self._dial_tone_counter = 0
                self._serial.write(byte)
                self._time_since_last_dial_tone = now