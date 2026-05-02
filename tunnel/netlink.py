# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
#netlink_version=202605012142
import sys

if __name__ == "__main__":
    print("This script should not be run on its own")
    sys.exit()

import socket
import time
import serial
from datetime import datetime
import logging
import threading
import select
import os
import platform
import requests
import subprocess
import errno
import re
import binascii
import configparser
import random
import stat
try:
    import sh
except ModuleNotFoundError:
    pass
import ipaddress
try:
    import dreampi
except ImportError:
    pass
try:
    import stun
except ImportError:
    os.system('pip install pystun3')
    import stun
    
class Netlink:
    pythonVer = platform.python_version_tuple()[0]
    osName = os.name
    if osName == 'posix': # should work on linux and Mac for USB modem, but untested.
        femtoSipPath = "/home/pi/dreampi/femtosip"
    else:
        femtoSipPath = os.path.realpath('./')+"/femtosip"
    # logger.setLevel(logging.INFO)
    packetSplit = b"<packetSplit>"
    dataSplit = b"<dataSplit>"
    timeout = 0.003

    def __init__(self, modem, verbose = False, printout = False):
        self.modem = modem
        self.pinging = True
        self.printout = printout
        self.data = []
        self.state = "starting"
        self.poll_rate = 0.01
        self.matching = True
        self.udp = None
        self.mode = "idle"
        self.ms = None
        self.dial_string = ""
        self.udp = None
        self.my_ip = None
        self.ext_port = None
        self.xband_timer = time.time()
        self.xband_init = False
        self.xband_sock = None
        self.xband_listening = False
        self.sip_ring = None
        self.usb_baud = 115200
        self.usb_timeout = 0.1
        self.usb = None
        self.tun_dc_ip = None
        self.dreamcast_ip = None
        self.usb_serial_port = "/dev/ttyUSB0"
        self.verbose = verbose
        self.dcnet = False
        self.dcnet_path = "/home/pi/dreampi/dcnet.rpi"
        # set up a way to use dial prefixes to change functionality
        self.dial_modifier = {
            "modifier": None,
            "modified": 0
        }

        if self.osName == 'posix':
            # Use existing logger exactly as-is
            self.logger = logging.getLogger('dreampi')

        else:
            # Fully controlled logger
            self.logger = logging.getLogger('Tunnel')
            self.logger.propagate = False
            level = logging.DEBUG if self.verbose else logging.INFO
            self.logger.setLevel(level)

            formatter = logging.Formatter(
                '%(asctime)s.%(msecs)03d %(levelname)-8s %(message)s',
                '%Y-%m-%d %H:%M:%S'
            )

            handler = logging.StreamHandler()
            handler.setLevel(level)
            handler.setFormatter(formatter)

            # Prevent duplicate handlers
            if not self.logger.handlers:
                self.logger.addHandler(handler)

        # <Netlink Server Addition>
        self.servers = {}
        self.read_config()

        # check for serial port on linux and configure
        if self.osName == 'posix':
            if self.usb_serial_port:
                try:
                    self.usb = serial.Serial(self.usb_serial_port, baudrate=self.usb_baud, rtscts=False, exclusive=True)
                    time.sleep(2) # Pyserial recommends giving OS 2 seconds to open port before changing settings
                    self.usb.rts = True
                    self.usb.timeout = self.usb_timeout
                    self.logger.info("Serial device found! Serial port monitoring started on %s. PPP available." % self.usb_serial_port)
                except serial.SerialException:
                    self.usb = None
            else:
                self.usb = None
        self.logger.debug("Netlink class initialized")

    def read_config(self):
        if self.osName == 'posix' and os.path.isfile("/boot/noautoupdates.txt"):
            self.logger.info("Dreampi script auto updates are disabled")
            return
        
        local_config = None
        upstream_data = None
        upstream_version = None

        config_paths = [
            '/boot/netlink_config.ini',
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'netlink_config.ini')
        ]
        for config_path in config_paths:
            if os.path.isfile(config_path):
                local_config = config_path
                break
            # if a config is placed in /boot it takes precedence over other config locations

        # Fallback if no config exists yet. By default same folder as this script.
        if not local_config:
            local_config = config_paths[1]
        
        def extract_version(data):
            for line in data.splitlines():
                try:
                    line = line.decode("utf-8")
                except Exception:
                    continue
                if "version" in line:
                    try:
                        return int(line.replace(" ","").split("version=", 1)[1].strip())
                    except ValueError:
                        return None
            return None

        try:
            # --- Fetch upstream file ---
            r = requests.get(
                "https://raw.githubusercontent.com/eaudunord/Netlink/main/tunnel/netlink_config.ini",
                timeout=10
            )
            r.raise_for_status()
            upstream_data = r.content

            upstream_version = extract_version(upstream_data)

        except requests.exceptions.SSLError:
            self.logger.info("SSL error while checking updates (check system time)")
            pass

        except requests.exceptions.RequestException as e:
            self.logger.info("Failed to download config: %s", e)
            pass


        # --- Read local file (if present) ---
        local_data = None
        local_version = None

        if os.path.isfile(local_config):
            with open(local_config, "rb") as f:
                local_data = f.read()
            local_version = extract_version(local_data)

        # --- Safety checks ---
        if upstream_version is None or upstream_data is None:
            self.logger.info("config has no upstream version; keeping local copy")

        elif local_version is not None and local_version >= upstream_version:
            self.logger.info("config is up to date (v%s)", local_version)

        # --- Write update ---
        elif (local_version is None) or (local_version < upstream_version):
            # Sections to preserve from local config
            preserve_sections = ['Serial Port', 'DCNet']
            preserved = {}

            if local_data:
                local_cfg = configparser.ConfigParser()
                local_cfg.read_string(local_data.decode("utf-8"))
                for section in preserve_sections:
                    if local_cfg.has_section(section):
                        preserved[section] = dict(local_cfg.items(section))

            # Write upstream as the new base
            with open(local_config, "wb") as f:
                f.write(upstream_data)

            # Re-apply preserved sections
            if preserved:
                merged_cfg = configparser.ConfigParser()
                merged_cfg.read(local_config)
                for section, values in preserved.items():
                    if not merged_cfg.has_section(section):
                        merged_cfg.add_section(section)
                    for key, val in values.items():
                        merged_cfg.set(section, key, val)
                with open(local_config, "w") as f:
                    merged_cfg.write(f)
                self.logger.info("Preserved local config sections: %s", list(preserved.keys()))

            self.logger.info("config updated (v%s to v%s)", local_version, upstream_version)

        if not os.path.isfile(local_config):
            self.logger.info("no config file found to parse")
            return


        cfg = configparser.ConfigParser()
        cfg.read(local_config)

        for section in cfg.sections():
            if section.startswith('server:'):
                code = section.split(':', 1)[1]
                self.servers[code] = dict(cfg.items(section))

        # Validate server codes. Don't just accept anything
        pattern = r'^1994\d{2}$'
        self.servers = {k: v for k, v in self.servers.items() if bool(re.match(pattern, k))}

        if self.servers:
            self.logger.info("Server ID codes loaded: %s", list(self.servers.keys()))

        # If running on dreampi check further for DCNet config and serial port config
        if self.osName == 'posix':
            
            try:
                serial_cfg = cfg['Serial Port']
                self.usb_serial_port = None if serial_cfg.get('disabled') == 'yes' else self.usb_serial_port
                self.usb_serial_port = serial_cfg.get('port', self.usb_serial_port)
                self.usb_baud = int(serial_cfg.get('baud', self.usb_baud))
                self.usb_timeout = float(serial_cfg.get('timeout', self.usb_timeout))
                self.logger.info("Serial configuration read")
            except (KeyError, ValueError):
                pass

            try:
                dcnet_cfg = cfg['DCNet']
                self.dcnet = True if dcnet_cfg.get('enabled') == 'yes' else False
                self.dcnet_path = dcnet_cfg.get('dcnet_path', self.dcnet_path)

                if self.dcnet:
                    if not os.path.isfile(self.dcnet_path):
                        self.dcnet = False
                        self.logger.warning("dcnet.rpi not found at %s" % self.dcnet_path)
                        dcnet_url = dcnet_cfg.get('dcnet_url')

                        if dcnet_url:
                            try:
                                with requests.get(dcnet_url, stream=True) as r:
                                    r.raise_for_status()
                                    with open(self.dcnet_path, "wb") as f:
                                        for chunk in r.iter_content(chunk_size=8192):
                                            f.write(chunk)
                                    self.dcnet = True
                                    self.logger.info("fetched missing dcnet.rpi successfully")
                            except (requests.exceptions.RequestException) as e:
                                self.logger.info("Error downloading dcnet.rpi: %s", e)
                            except (FileNotFoundError) as e:
                                self.logger.info("Check dcnet location in config. Error: %s", e)
                    # Check if executable - current or freshly downloaded file
                    if os.path.isfile(self.dcnet_path):
                        st = os.stat(self.dcnet_path)
                        if not bool(st.st_mode & stat.S_IXUSR):
                            os.chmod(self.dcnet_path, st.st_mode | stat.S_IXUSR)
                            self.logger.info("dcnet.rpi made executable")

                self.logger.info("DCNet configuration read")
                self.logger.info("DCNet available: %s", self.dcnet)
                if self.dcnet:
                    self.logger.info("Add *69 to outside dial prefix to activate DCNet")

            except KeyError:
                pass

    def hexlify(self, data):
        return ' '.join('{:02X}'.format(ord(c) if isinstance(c, str) else c) for c in data)
    
    def digit_parser(self):
        last_heard = time.time()
        raw_string = ""
        tel_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '#']
        char = self.modem._serial.read(1).decode()
        if char in tel_digits:
            raw_string += char
            while True:
                if time.time() - last_heard > 2:
                    break
                try:
                    char = self.modem._serial.read(1).decode() #first character was <DLE>, what's next?
                    if ord(char) == 16:
                        continue
                    if char in tel_digits:
                        last_heard = time.time()
                        raw_string += char
                except (TypeError, ValueError):
                    pass
        if raw_string in ["0", "00"]:
            self.ms = "waiting"
            self.mode = "netlink"
            self.dial_string = raw_string
            return {'client':self.mode,'dial_string':raw_string}
        # <Netlink Server Addition>
        elif raw_string in self.servers:
            self.mode = "netlink_server"
            self.dial_string = raw_string
            self.logger.debug("Netlink server connection requested")
            return {'client':self.mode,'dial_string':raw_string}
         # </Netlink Server Addition>
        elif raw_string == "*70":
            self.logger.info("Call waiting disabled")
            self.mode = "idle"
            self.dial_string = ""
            return {'client':self.mode, 'dial_string':raw_string}
        elif raw_string == "*69":
            self.logger.info("*69: DCNet connection requested")
            if self.dcnet:
                self.dial_modifier.update({"modifier":"dcnet","modified": time.time()})
            self.mode = "idle"
            self.dial_string = ""
            return {'client':self.mode, 'dial_string':raw_string}
        elif raw_string in ["18002071194","19209492263","0120717360","0355703001"]:
            self.mode = "xband_server"
            self.dial_string = ""
            self.logger.debug("xband server called")
            return {'client':self.mode, 'dial_string':raw_string}
        elif raw_string == "0642542154":
            self.mode = "capcom"
            self.dial_string = ""
            return {'client': self.mode, 'dial_string': raw_string}
        elif raw_string.startswith("#") and raw_string.endswith("#"):
            dial_string = raw_string.replace("#","")
            if len(dial_string) == 3 and dial_string[0] == "0": # This condition indicates a game is waiting for a call
                self.ms = "waiting"
                self.mode = "netlink"
                self.dial_string = dial_string
                return {'client':self.mode,'dial_string':raw_string}
            elif len(dial_string.split('*')) == 5 and dial_string.split('*')[-1] == "1": # xband format
                self.ms = "calling"
                self.mode = "xband_connect"
                self.dial_string = '.'.join(dial_string.split('*')[0:4])
                return {'client':self.mode,'dial_string':raw_string}
            elif len(dial_string.split('*')) == 4: # IP dialing format
                self.ms = "calling"
                self.mode = "netlink"
                self.dial_string = '.'.join([str(int(oct)) for oct in dial_string.split('*')])
                return {'client':self.mode,'dial_string':raw_string}
            elif len(dial_string) == 12: # IP dialing format
                #if we have a full 12 digit string add in '.' every three characters
                try:
                    int(dial_string)
                    self.dial_string = '.'.join(dial_string[i:i+3] for i in range(0, len(dial_string), 3))
                    self.ms = "calling"
                    self.mode = "netlink"
                    return {'client':self.mode,'dial_string':raw_string}
                except TypeError: # there are other characters in the string. I don't know what this is.
                    self.mode = "idle"
                    self.dial_string = ""
                    return {'client':self.mode,'dial_string':raw_string}
            else:
                self.ms = "calling"
                self.mode = "netlink"
                self.dial_string = dial_string
                self.logger.debug("Netlink matchmaking call")
                return {'client':self.mode,'dial_string':raw_string}             
        else:
            if len(raw_string) > 0: # any sequence that we don't recognize, assume is meant to be PPP
                self.ms = None
                # Check for dial modifiers
                if time.time() - self.dial_modifier.get('modified') < 10:
                    self.mode = self.dial_modifier.get('modifier', 'PPP')
                else:
                    self.mode = "PPP"
                self.dial_string = ""
                return {'client':self.mode,'dial_string':raw_string}
            else:
                # self.mode = "idle"
                self.dial_string = ""
                return {'client':"idle",'dial_string':raw_string}

    def initConnection(self):
        result = ["failed", None]
        self.my_ip = None
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        opponent = self.dial_string.replace('*','.')
        ip_set = opponent.split('.')
        for i,set in enumerate(ip_set): #socket connect doesn't like leading zeroes now
            fixed = str(int(set))
            ip_set[i] = fixed
        opponent = ('.').join(ip_set)
        registered = False
        last_STUN = 0
        my_ip, ext_port = [None, None]

        if self.ms == "waiting":
            self.logger.info("Waiting")
            registered = False
            timerStart = time.time()
            PORT = 65432
            tcp.settimeout(20)
            tcp.bind(('', PORT))
            tcp.listen(5)
            while True:
                if time.time() - timerStart > 120:
                    if len(self.dial_string) == 3 and registered:
                        self.timed_out(self.dial_string[-2:], self.my_ip)
                    result = ["failed", None]
                    break
                ready = select.select([tcp], [], [],0) # listen for the traditional direct connection attempt
                if ready[0]:
                    conn, addr = tcp.accept()
                    opponent = addr[0]
                    self.logger.info('Connection from %s' % str(opponent))
                    while True:
                        try:
                            data = conn.recv(1024)
                        except socket.error: #first try can return no payload
                            continue
                        if data == b'readyip':
                            conn.sendall(b'g2gip')
                            self.logger.info("Sending Ring")
                            self.modem._serial.write(("RING\r\n").encode())
                            self.modem._serial.write(("CONNECT\r\n").encode())
                            self.logger.info("Ready for Data Exchange!")
                            if registered:
                                self.timed_out(self.dial_string[-2:], self.my_ip)
                            result = ["connected", (opponent, 20002)]
                            return result
                        if not data:
                            self.logger.info("Failed to init")
                            break
                if len(self.dial_string) == 3: # matchmaking is on by default
                    if self.matching:
                        if time.time() - last_STUN > 5:
                            my_ip, ext_port = self.getWanIP(20001) # Periodically STUN to maintain port mapping, discover if changes.
                            last_STUN = time.time()
                        if my_ip and ext_port: # only update if the function returns good info
                            self.my_ip = my_ip
                            self.ext_port = ext_port 
                        if self.my_ip:
                            if not registered:
                                if self.register(self.dial_string[-2:], self.my_ip, self.ext_port):
                                    registered = True
                            elif registered:
                                status, opponent = self.get_status(self.dial_string[-2:], self.my_ip)
                                if status:
                                    self.logger.info("Sending Ring")
                                    self.modem._serial.write(("RING\r\n").encode())
                                    self.modem._serial.write(("CONNECT\r\n").encode())
                                    self.logger.info("Ready for Data Exchange!")
                                    result = ["connected",opponent]
                                    break
                        else:
                            self.logger.info("Couldn't get WAN information. Won't register for match. Trying again in 1 second")
                        time.sleep(1)


        if self.ms == "calling":
            
            if len(self.dial_string) > 3: # treat the call as a direct dial attempt
                self.logger.info("Calling")
                PORT = 65432
                tcp.settimeout(20)
                try:
                    tcp.connect((opponent, PORT))
                    tcp.sendall(b"readyip")
                    ready = select.select([tcp], [], [])
                    if ready[0]:
                        data = tcp.recv(1024)
                        if data == b'g2gip':
                            self.logger.info("Ready for Data Exchange!")
                            #tcp.shutdown(socket.SHUT_RDWR)
                            #tcp.close()
                            result = ["connected", (opponent, 20001)]
                except socket.error:
                    self.logger.info("Couldn't connect to opponent. Port not open or timed out")
                    self.logger.debug(str(opponent))
                    return ["failed", ""]
            else:
                if self.dial_string == "999":
                    self.matching = False
                    self.logger.info("Matchmaking disabled")
                elif self.dial_string == "888":
                    self.matching = True
                    self.logger.info("Matchmaking enabled")
                else: # connect to the matchmaking server and get a match
                    my_ip, ext_port = self.getWanIP(20002)
                    if my_ip and ext_port: # only update if the function returns good data
                        self.my_ip = my_ip
                        self.ext_port = ext_port
                    if self.my_ip:
                        status, opponent = self.get_match(self.dial_string[-2:], self.my_ip, self.ext_port)
                        if status:
                            result = ["connected", opponent]
                            
        tcp.close()
        return result


    def register(self, game_id, ip_address, port):
        params = {"action" : 'wait', 
                    "gameID" : game_id, 
                    "client_ip" : ip_address, 
                    "port" : port, 
                    "key" :'mySuperSecretSaturnKey1234'
                }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"}
        url = "https://saturn.dreampipe.net/match_service.php?"
        try:
            r=requests.get(url, params=params, headers=headers)
            r.raise_for_status()
            self.logger.info("Registered for a match")
            return True
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            self.logger.info("Couldn't connect to matching server")
            self.logger.info(e)
            return False
        
    def get_status(self, game_id, ip_address):
        params = {"action" : 'status', 
                    "gameID" : game_id, 
                    "client_ip" : ip_address, 
                    "key" :'mySuperSecretSaturnKey1234'
                }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"}
        url = "https://saturn.dreampipe.net/match_service.php?"
        try:
            r=requests.get(url, params=params, headers=headers)
            r.raise_for_status()
            status = r.json()["status"]
            if status == "matched":
                dial_string = r.json()["opponent ip_address"]
                address, oppPort = dial_string
                oppPort = int(oppPort)
                opponent = '.'.join(str(int(address[i:i+3])) for i in range(0, len(address), 3))
                return [True, (opponent, oppPort)]
            else:
                return [False, (None, None)]
            
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            self.logger.info("Couldn't connect to matching server")
            return [False, (None, None)]

    def get_match(self, game_id, ip_address, port):
        params = {"action" : 'match', 
                    "gameID" : game_id, 
                    "client_ip" : ip_address, 
                    "port" : port, 
                    "key" :'mySuperSecretSaturnKey1234'
                }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"}
        url = "https://saturn.dreampipe.net/match_service.php?"
        try:
            r=requests.get(url, params=params, headers=headers)
            r.raise_for_status()
            status = r.json()["status"]
            self.logger.info(status)
            if status == "found opponent":
                dial_string = r.json()["opponent ip_address"]
                address, oppPort = dial_string
                oppPort = int(oppPort)
                opponent = '.'.join(str(int(address[i:i+3])) for i in range(0, len(address), 3))
                return [True, (opponent, oppPort)]
            else:
                return [False, (None, None)]
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
            self.logger.info("Couldn't connect to matching server")
            self.logger.info(e)
            return [False, (None, None)]

    def timed_out(self, game_id, ip_address):
        params = {"action" : 'timeout', 
                    "gameID" : game_id, 
                    "client_ip" : ip_address, 
                    "key" :'mySuperSecretSaturnKey1234'
                }
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"}
        url = "https://saturn.dreampipe.net/match_service.php?"
        try:
            r=requests.get(url, params=params, headers=headers)
            r.raise_for_status()
            self.logger.info("Wait timed out. Deregistered from matching server")
        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
            self.logger.info("Couldn't connect to matching server")
            return False, None

    def getWanIP(self, Port):
        if not self.udp:
            self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 184)
            self.udp.settimeout(2)
            self.udp.bind(('', Port))

        try:
            nat_type, info  = stun.get_nat_type(s=self.udp, source_ip='', source_port=Port, stun_host="stun.l.google.com", stun_port=19302)
            external_ip = info['ExternalIP']
            external_port = info['ExternalPort']
            external_ip = "".join([x.zfill(3) for x in external_ip.split(".")])
        except AttributeError:
            self.logger.info("Couldn't get WAN information")
            return None, None
        except KeyError: # it's possible for initial tunnel data to be interpreted as a STUN response depending on timing and it'll throw an exception
            self.logger.info("Ignoring invalid response")
            return None, None
        return external_ip, external_port

    def listener(self, opponent):
        self.logger.debug("listener thread started")
        self.logger.info(self.state)
        last_ping_sent = 0
        lastPing = 0
        ping = 0
        pong_counter = 0
        pong = time.time()
        jitterStore = []
        pingStore = []
        currentSequence = 0
        maxPing = 0
        maxJitter = 0
        recoveredCount = 0
        established = False

        while(self.state != "netlink_disconnected"):
            if time.time() - ping > 1:
                # Ping and keepalive
                try:
                    self.udp.sendto(b'PING_SHIRO', opponent)
                    last_ping_sent = time.time()
                except ConnectionResetError:
                    pass
                ping = time.time()
            ready = select.select([self.udp],[],[],0.001)
            if ready[0]:

                packetSet, remote = self.udp.recvfrom(1024)

                if packetSet == b'PING_SHIRO':
                    try:
                        self.udp.sendto(b'PONG_SHIRO', opponent)
                    except ConnectionResetError:
                        pass
                    continue
                elif packetSet == b'PONG_SHIRO':
                    pong_counter += 1
                    if not established:
                        self.logger.info("Connection established")
                        established = True
                    pong = time.time()
                    pingResult = round((pong-last_ping_sent)*1000,2)
                    if pingResult > 500:
                        continue
                    if pingResult > maxPing:
                        maxPing = pingResult
                    pingStore.insert(0,pingResult)
                    if len(pingStore) > 20:
                        pingStore.pop()
                    jitter = round(abs(pingResult-lastPing),2)
                    if jitter > maxJitter:
                        maxJitter = jitter
                    jitterStore.insert(0,jitter)
                    if len(jitterStore) >20:
                        jitterStore.pop()
                    jitterAvg = round(sum(jitterStore)/len(jitterStore),2)
                    pingAvg = round(sum(pingStore)/len(pingStore),2)
                    if self.osName != 'posix':
                        sys.stdout.write('Ping: %s Max: %s | Jitter: %s Max: %s | Avg Ping: %s |  Avg Jitter: %s | Recovered Packets: %s         \r' % (pingResult,maxPing,jitter, maxJitter,pingAvg,jitterAvg,recoveredCount))
                    elif self.osName == 'posix' and pong_counter >= 10:
                        self.logger.info('Ping: %s Max: %s | Jitter: %s Max: %s | Avg Ping: %s |  Avg Jitter: %s | Recovered Packets: %s' % (pingResult,maxPing,jitter, maxJitter,pingAvg,jitterAvg,recoveredCount))
                    if pong_counter >= 10:
                        pong_counter = 0
                    lastPing = pingResult
                    continue
                elif packetSet == b'OPEN_SHIRO':
                    continue
                #end pinging code block
                
                packets= packetSet.split(self.packetSplit)
                try:
                    while True:
                        packetNum = 0
                        
                        #go through all packets 
                        for p in packets:
                            if int(p.split(self.dataSplit)[1]) == currentSequence:
                                break
                            packetNum += 1
                            
                        #if the packet needed is not here,  grab the latest in the set
                        if packetNum == len(packets):
                            packetNum = 0
                        if packetNum > 0 :
                            recoveredCount += 1
                        message = packets[packetNum]
                        payload = message.split(self.dataSplit)[0]
                        sequence = message.split(self.dataSplit)[1]
                        if int(sequence) < currentSequence:
                            break  #All packets are old data, so drop it entirely
                        
                        currentSequence = int(sequence) + 1
                        
                        toSend = payload
                        if self.printout:
                            self.logger.debug("received: " + self.hexlify(toSend))
                        self.modem._serial.write(toSend)
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except (IndexError, ValueError):
                    continue
        self.close_udp()            
        self.logger.info("Listener stopped")        
                    
    def sender(self, opponent):
        self.logger.info("Sending")
        self.logger.debug("Sending thread started. Sending to %s" % str(opponent))
        sequence = 0
        packets = []
        self.modem._serial.timeout = None

        # UDP send to improve hole punching probability
        try:
            self.udp.sendto(b'OPEN_SHIRO', opponent)
        except ConnectionResetError:
            pass
        
        while(self.state != "netlink_disconnected"):
            new = self.modem._serial.read(1) #should now block until data. Attempt to reduce CPU usage. I don't know if this is better or not
            # alternatively just check if self.modem._serial.in_waiting is greater than 0
            raw_input = new + self.modem._serial.read(self.modem._serial.in_waiting)
            if b"NO CARRIER" in raw_input:
                print('')
                self.logger.info("NO CARRIER")
                self.state = "netlink_disconnected"
                time.sleep(1)
                self.close_udp()
                self.logger.info("Sender stopped")
                return
            if not self.modem._serial.cd:
                print('')
                self.logger.info("NO CD")
                self.state = "netlink_disconnected"
                time.sleep(1)
                self.close_udp()
                self.logger.info("Sender stopped")
                return                
            
            try:
                payload = raw_input
                seq = str(sequence)
                if len(payload) > 0:
                    
                    packets.insert(0,(payload+self.dataSplit+seq.encode()))
                    if(len(packets) > 5):
                        packets.pop()
                    for i in range(2): #send the data twice. May help with drops or latency    
                        ready = select.select([],[self.udp],[]) #blocking select  
                        if ready[1]:
                            try:
                                self.udp.sendto(self.packetSplit.join(packets), opponent)
                            except ConnectionResetError:
                                pass

                    if self.printout:
                        self.logger.debug("sent: " + self.hexlify(payload))        
                    sequence+=1
            except:
                continue
    
    def netlink_exchange(self, state, opponent):  
        self.state = state           
        if self.state == "connected":
            t1 = threading.Thread(target=self.listener, args=(opponent,))
            t2 = threading.Thread(target=self.sender,args=(opponent,))
            if self.ms == "waiting": #we're going to bind to a port. Some users may want to run two instances on one machine, so use different ports for waiting, calling
                Port = 20001
            if self.ms == "calling":
                Port = 20002
            if not self.udp:
                self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 184)
                self.udp.bind(('', Port))
            self.udp.settimeout(0.0) # non blocking. Should use select when reading or writing to ensure the socket is available.
            self.logger.debug("starting data exchange. %s. UDP bound to port: %s" % (self.ms, self.udp.getsockname()[1]))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

    def do_netlink(self):
        self.modem.stop_dial_tone()
        self.close_udp()
        try:
            self.modem.connect_netlink(speed=57600,timeout=0.01,rtscts = True) #non-blocking version
            self.modem.query_modem(b'AT%E0\V1')
            self.modem.query_modem(b'AT%C0\N3')
            self.modem.query_modem(b'AT&C1&D2')
            # self.modem.query_modem(b'AT+MS=V32b,1,14400,14400,14400,14400') probably not necessary to be so explicit with rates and modulation
            # self.modem.query_modem(b"ATA", timeout=30, response = "CONNECT")
        except IOError:
            return
        if not self.modem_answer():
            return
        state, opponent  = self.initConnection()
        if state == "failed":
            for i in range(3): # escape sequence
                self.modem._serial.write(b'+')
                time.sleep(0.2)
            time.sleep(4)
            self.modem.send_command('ATH0')
            return
        self.netlink_exchange(state, opponent)

    def getserial(self):
        cpuserial = b"0000000000000000"
        if self.osName == 'posix':
            try:
                f = open('/proc/cpuinfo','r')
                for line in f:
                    if line[0:6]=='Serial':
                        cpuserial = line[10:26].encode()
                f.close()
                self.logger.info("Found valid CPU ID")
            except:
                cpuserial = b"ERROR000000000"
                self.logger.info("Couldn't find valid CPU ID, using error ID")
        else:
            cpuserial = subprocess.check_output(["wmic","cpu","get","ProcessorId","/format:csv"]).strip().split(b",")[-1]
            self.logger.info("Found valid CPU ID")
        return cpuserial

    def xband_server(self):
        self.modem.stop_dial_tone()
        if not self.modem_answer():
            return
        self.modem._serial.timeout = 1
        self.logger.info("connecting to retrocomputing.network")
        s = socket.socket()
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.setblocking(False)
        s.settimeout(15)
        s.connect(("xbserver.retrocomputing.network", 56969))
        # cpu = subprocess.check_output(["wmic","cpu","get","ProcessorId","/format:csv"]).strip().split(b",")[-1]
        hwid = self.getserial()
        sdata = b"///////PI-" + hwid + b"\x0a"
        sentid = 0
        self.logger.info("connected")
        while True:
            try:
                ready = select.select([s], [], [],0.3)
                if ready[0]:
                    data = s.recv(1024)
                    # print(data)
                    self.modem._serial.write(data)
                if sentid == 0:
                    s.send(sdata)
                    sentid = 1
            except socket.error as e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    time.sleep(0.1)
                else:
                    self.logger.warn("tcp connection dropped")
                    break
            if not self.modem._serial.cd:
                self.logger.info("1: CD is not asserted")
                time.sleep(2.0)
                if not self.modem._serial.cd:
                    self.logger.info("CD still not asserted after 2 sec - xband hung up")
                    break
            if sentid == 1:        
                if self.modem._serial.in_waiting:
                    line = b""
                    while True:
                        data2 = self.modem._serial.read(1)
                        line += data2
                        if b"\x10\x03" in line: #this is used to indicate end of line/data
                            # print(line)
                            s.send(line)
                            break
                        if not self.modem._serial.cd:
                            self.logger.info("2: CD is not asserted")
                            time.sleep(2.0)
                            if not self.modem._serial.cd:
                                self.logger.info("CD still not asserted after 2 sec - xband hung up")
                                break
        s.close()
        self.logger.info("Xband disconnected. Back to listening")
        self.mode = "xband_matching"
        self.ms = "waiting"
        self.modem.connect()
        self.modem.start_dial_tone()
        return
    
    def xband_match(self):
        if self.udp:
            self.close_udp()
        if self.xband_init == False:
            self.xband_setup()
        if time.time() - self.xband_timer < 15: # an xband call should start right away. Don't listen if you don't have to.
            self.logger.debug("Exiting xband_match function. t < 15")
            return
        if time.time() - self.xband_timer > 900:
            self.mode = "idle"
            self.close_xband()
            self.logger.debug("Exiting xband_match function. t > 900")
            return
        if not self.xband_sock:
            self.open_xband()
            self.logger.info("Listening for xband call")
        xbandResult,opponent = self.xband_listen()
        if xbandResult == "connected":
            self.netlink_exchange(state = "connected", opponent = (opponent, 20002))
            self.logger.info("Xband Disconnected")
            self.mode = "idle"
            self.modem.connect()
            self.modem.start_dial_tone()
            self.close_xband()

    def xband_setup(self):
        if not os.path.exists(self.femtoSipPath): # femtosip is not distributed with the rest of these scripts. Only fetched if needed.
            self.logger.debug("Femtosip folder not found. Downloading component")
            try:
                os.makedirs(self.femtoSipPath)
                r = requests.get("https://raw.githubusercontent.com/eaudunord/femtosip/master/femtosip.py")
                r.raise_for_status()
                with open(self.femtoSipPath+"/femtosip.py",'wb') as f:
                    text = r.content.decode('ascii','ignore').encode()
                    f.write(text)
                self.logger.info('fetched femtosip')
                r = requests.get("https://github.com/astoeckel/femtosip/raw/master/LICENSE")
                r.raise_for_status()
                with open(self.femtoSipPath+"/LICENSE",'wb') as f:
                    f.write(r.content)
                self.logger.info('fetched LICENSE')
                with open(self.femtoSipPath+"/__init__.py",'wb') as f:
                    pass
                self.xband_init = True
                self.logger.debug("Femtosip downloaded")
            except requests.exceptions.HTTPError:
                self.logger.info("unable to fetch femtosip")
                return "dropped"
            except OSError:
                self.logger.info("error creating femtosip directory")
        else:
            self.logger.debug("Femtosip folder found")
            self.xband_init = True
        

    def open_xband(self):
        if not self.xband_sock:
            self.logger.debug("open_xband. Listening socket created")
            PORT = 65433
            self.xband_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.xband_sock.setblocking(0)
            self.xband_sock.bind(('', PORT))
            self.xband_sock.listen(5)
        self.xband_listening = True
        self.logger.debug("open_xband. Listening socket exists")

    def close_xband(self):
        try:
            if self.xband_sock:
                self.xband_sock.close()
                time.sleep(2)
                self.xband_sock = None
            self.xband_listening = False
        except:
            self.logger.debug("problem closing listening xband socket")
            pass

    def close_udp(self):
        if self.udp:
            self.udp.close()
            self.udp = None

    def xband_listen(self):
        result = ("nothing","")
        ready = select.select([self.xband_sock], [], [],0)
        if ready[0]:
            self.logger.info("incoming xband call")
            conn, addr = self.xband_sock.accept()
            opponent = addr[0]
            callTime = time.time()
            while True:
                ready = select.select([conn], [], [],0)
                if ready[0]:
                    data = conn.recv(1024)
                    if data == b"RESET":
                        self.modem.stop_dial_tone()
                        self.init_xband()
                        conn.sendall(b'ACK RESET')
                    elif data == b"RING":
                        self.logger.info("RING")
                        conn.sendall(b'ANSWERING')
                        time.sleep(6)
                        self.logger.info('Answering')
                        try:
                            self.modem.query_modem(b"ATX1D", timeout=30, response = "CONNECT")
                        except IOError:
                            self.logger.info("Couldn't answer call")
                            self.reset()
                            result = ("dropped","")
                            break
                        self.logger.info("CONNECTED")
                    elif data == b"PING":
                        conn.sendall(b'ACK PING')
                        self.modem._serial.timeout=None
                        self.modem._serial.write(b'\xff')
                        while True:
                            char = self.modem._serial.read(1) #read through the buffer and skip all 0xff
                            if char == b'\xff':
                                continue
                            elif char == b'\x01':
                                conn.sendall(b'RESPONSE')
                                self.logger.info('got a response')
                                break
                        if self.modem._serial.cd: #if we stayed connected
                            continue
                            
                        elif not self.modem._serial.cd: #if we dropped the call
                            self.logger.info("Xband Disconnected")
                            self.modem.connect()
                            self.modem.start_dial_tone()
                            result = ("dropped","")
                            break
                        
                    elif data == b'RESPONSE':
                        self.modem._serial.write(b'\x01')
                        if self.modem._serial.cd:
                            result = ("connected",opponent)
                            break
                        
                    if time.time() - callTime > 120:
                        break
        self.logger.debug("xband_listen exited. Result: %s" % str(result))
        return result
    
    def init_xband(self):
        self.modem.stop_dial_tone()
        self.modem.connect_netlink(speed=57600,timeout=0.05,rtscts=True)
        self.modem.query_modem(b'AT%E0')
        self.modem.query_modem(b"AT\V1%C0")
        self.modem.query_modem(b'AT+MS=V22b')

    def ring_phone(self):
        import femtosip.femtosip as sip_ring
        result = "hangup"
        opponent = self.dial_string
        opponent_id = "11"
        opponent_port = 4000
        PORT = 65433
        self.close_udp()
        sock_send = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock_send.settimeout(15)
        self.logger.info("Calling opponent")
        try:
            r = requests.get("http://myipv4.p1.opendns.com/get_my_ip")
            r.raise_for_status()
            my_ip = r.json()['ip']
        except requests.exceptions.HTTPError:
            self.logger.info("Couldn't get WAN IP")
            my_ip = "127.0.0.1"
        except requests.exceptions.SSLError:
            self.logger.info("Couldn't get WAN IP")
            my_ip = "127.0.0.1"

        try:
            sock_send.connect((opponent, PORT))
            sock_send.sendall(b"RESET")
            sentCall = time.time()
            while True:
                ready = select.select([sock_send], [], [],0)
                if ready[0]:
                    data = sock_send.recv(1024)
                    if data == b'ACK RESET':
                        try:
                            sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,protocol="udp")
                            sip.call(opponent_id,3)
                        except Exception as e:
                            self.logger.info("Error calling VoIP: %s" % e)
                            result = "hangup"
                            break 
                        sock_send.sendall(b'RING')
                    elif data == b'ANSWERING':
                        self.logger.info("Answering")
                        self.modem_answer()
                        self.logger.info("CONNECTED")
                        sock_send.sendall(b'PING')

                    elif data == b"ACK PING":
                        self.modem._serial.timeout=None
                        self.modem._serial.write(b'\xff')
                        while True:
                            char = self.modem._serial.read(1) #read through the buffer and skip all 0xff
                            if char == b'\xff':
                                continue
                            elif char == b'\x01':
                                # modem._serial.write(b'\x01')
                                self.logger.info("got a response")
                                sock_send.sendall(b'RESPONSE')
                                break
                        if self.modem._serial.cd: #if we stayed connected
                            continue
                            
                        elif not self.modem._serial.cd:
                            #if we dropped the call
                            result =  "hangup"
                            break

                    elif data == b'RESPONSE':
                        self.modem._serial.write(b'\x01')
                        result = "connected"
                        break
                if time.time() - sentCall > 90:
                    self.logger.info("opponent tunnel not responding")
                    result = "hangup"
                    break

        except socket.error:
            self.logger.info("couldn't connect to opponent")
            result = "hangup"
        
        sock_send.close()
        self.logger.debug("ring_phone exited. Result: %s" % str(result))
        return result

    def reset(self):
        self.modem.stop_dial_tone()
        # self.modem.reset()
        self.modem.connect()
        try:
            if self.modem._serial.in_waiting:
                self.modem._serial.read(self.modem._serial.in_waiting)
        except Exception:
            pass
        self.modem.start_dial_tone()
        self.mode = "idle"
        self.state = "starting"

    def serial_poll(self):
        if self.usb:
            try:
                if self.usb.in_waiting:
                    payload = self.usb.read_until(b'\n')
                    if len(payload) > 0:
                        # if garbage is read, assume the baud rate is wrong
                        # try:
                        #     payload.decode('utf-8')
                        # except UnicodeDecodeError:
                        #     # self.logger.info("serial port: %s" % binascii.hexlify(payload))
                        #     # Don't switch on GDEMU/openMenu garbage
                        #     if payload == b'\x00\xfb\x00':
                        #         pass
                        #     else:
                        #         self.baud_index = (self.baud_index + 1) % len(self.valid_bauds)
                        #         self.usb.baudrate = self.valid_bauds[self.baud_index]
                        #         self.logger.info("Baud rate mismatch. Trying: %s" % self.usb.baudrate)
                        #         return
                        self.logger.info("serial port: %s" % payload.strip())
                        if payload[:2] == b'AT':
                            if payload == b'AT\r\n' or payload == b'AT\n':
                                self.usb.write(b'OK\r\n')
                            elif payload == b'ATZ\r\n' or payload == b'ATZ\n':
                                self.usb.write(b'OK\r\n')
                            elif payload[:4] == b'ATDT':
                                self.usb.write(b'CONNECT ' + str(self.usb.baudrate).encode() + b'\r\n')
                                self.logger.info("Call answered!")

                                options = [
                                    "local",
                                    "lcp-echo-interval", "5",
                                    "lcp-echo-failure", "2",
                                    "lcp-max-terminate", "1",
                                    "novj",
                                    "debug",
                                    "ktune",
                                    "noccp",
                                    "noauth"
                                ]    

                                self.pppd_run(device = self.usb_serial_port, speed = self.usb.baudrate, options = options )

                                if self.usb and self.usb.is_open:
                                    self.usb.flush() #added a flush, is data hanging on in the buffer?
                                    self.usb.close()
                                    self.usb = None
                                self.logger.info("CONNECT")
                                self.mode = "serial_ppp"
                            else:
                                self.usb.write(b'OK\r\n')
            except IOError:
                self.logger.info("USB serial device disconnected. Stopping serial port monitoring")
                self.usb = None
        else:
            return 0
        
    def serial_ppp(self):
        
        from dcnow import DreamcastNowService
        dcnow = DreamcastNowService()
        dcnow.go_online("")

            
        for line in sh.tail("-f", "/var/log/messages", "-n", "1", _iter=True):
            if "pppd" in line and "Exit" in line:#wait for pppd to execute the ip-down script
                self.logger.info("Detected modem hang up, going back to listening")
                break
            if "pppd" in line and "Connection terminated." in line:
                self.logger.info("pppd ip-down finished")
                try:
                    print(subprocess.check_output(['sudo', 'killall', 'pppd']))
                    self.logger.info("kill 1")
                    time.sleep(5)
                    print(subprocess.check_output(['sudo', 'killall', 'pppd']))
                    self.logger.info("kill 2")
                    # why do I have to do this twice? pppd doesn't detect a hangup when ppp disconnects.
                    # a cleaner solution would be preferable but this works
                except Exception as e:
                    print(e)
        dreampi.remove_alias_interface()
        dcnow.go_offline() #changed dcnow to wait 15 seconds for event instead of sleeping. Should be faster.
        self.mode = "idle"
        try:
            self.usb = serial.Serial(self.usb_serial_port, baudrate=self.usb_baud, rtscts=False, exclusive=True)
            self.usb.rts = True
            self.usb.timeout = self.usb_timeout
            self.baud_index = 0
        except:
            self.logger.info("No active serial port detected")
            self.usb = None
        self.logger.info('Reset serial port')

    #<Netlink Server Addition>
    def netlink_server(self):
        if self.servers:
            server = self.servers.get(self.dial_string)
        else:
            server = None
        if server:
            server_type = server.get('handler', 'server')
            if server_type == 'transparent':
                self.netlink_transparent_server(server)
            else:
                self.netlink_standard_server(server)

        else:
            self.logger.info("Couldn't find a matching config")

    def netlink_transparent_server(self, server_cfg):
        """
        Transparent proxy handler for BBS-protocol games (e.g. Dragon's Dream).
        Answers modem, connects to TCP server, relays ALL data bidirectionally.
        Does NOT flush serial buffer after CONNECT — the Saturn sends BBS
        commands immediately and the server must see them.
        """
        host = server_cfg.get('host', '127.0.0.1')
        port = int(server_cfg.get('port', '8020'))
        label = server_cfg.get('name', host)

        self.modem.stop_dial_tone()

        # 1. Answer the call
        if self.modem_answer():
            self.logger.info("%s: Modem Linked", label)
        else:
            self.logger.info("%s: ATA failed", label)
            return

        # 2. Connect to TCP server IMMEDIATELY — no serial flush!
        # The Saturn sends BBS commands right away and the server must see them.
        try:
            s = socket.socket()
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.settimeout(5)
            s.connect((host, port))
            self.logger.info("%s: Tunnel Established to %s:%d", label, host, port)
            s.setblocking(False)
        except Exception as e:
            self.logger.info("%s: Connection failed: %s", label, e)
            return

        # 3. Transparent relay — no flush, no auth, no filtering
        self.modem._serial.timeout = 0
        modem_tail = b""
        while True:
            had_data = False

            # Server -> Saturn
            try:
                data = s.recv(4096)
                if data:
                    self.modem._serial.write(data)
                    had_data = True
                else:
                    self.logger.info("%s: Server closed connection", label)
                    break
            except socket.error:
                pass

            # Saturn -> Server
            if self.modem._serial.in_waiting:
                data = self.modem._serial.read(self.modem._serial.in_waiting)
                if data:
                    had_data = True
                    modem_tail = (modem_tail + data)[-32:]
                    if b"NO CARRIER" in modem_tail:
                        self.logger.info("%s: NO CARRIER", label)
                        break
                    s.send(data)

            # Carrier Detect check
            if not self.modem._serial.cd:
                time.sleep(1.0)
                if not self.modem._serial.cd:
                    self.logger.info("%s: Saturn hung up", label)
                    break

            if not had_data:
                time.sleep(0.005)

        s.close()
        self.logger.info("%s: Session Closed", label)

    def netlink_standard_server(self, server_cfg):
        """
        Handle server connection from config.
        Answers the modem, connects to the configured TCP server,
        authenticates if configured, and relays data bidirectionally.
        """
        host = server_cfg['host']
        port = int(server_cfg['port'])
        shared_secret = server_cfg.get('shared_secret', '').encode() if server_cfg.get('shared_secret') else None
        auth_magic = server_cfg.get('auth_magic', 'AUTH').encode()
        auth_timeout = float(server_cfg.get('auth_timeout', '5.0'))
        label = server_cfg.get('name', host)

        self.modem.stop_dial_tone()

        # Answer the modem call (same pattern as xband_server)
        if not self.modem_answer():
            self.logger.info("%s: ATA failed or timed out", label)
            return

        self.modem._serial.timeout = 0  # non-blocking for relay polling

        # Flush any leftover CONNECT response / modem noise from serial buffer
        time.sleep(0.2)
        while self.modem._serial.in_waiting:
            self.modem._serial.read(self.modem._serial.in_waiting)
            time.sleep(0.05)

        # Connect to server via TCP
        try:
            server_ip = socket.gethostbyname(host)
        except socket.gaierror as e:
            self.logger.warn("%s: DNS resolution failed: %s" % (label, e))
            return

        s = socket.socket()
        s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        s.settimeout(10)
        try:
            s.connect((server_ip, port))
            self.logger.info("%s: connected to %s:%d",
                             label, server_ip, port)
        except (socket.error, OSError) as e:
            self.logger.warn("%s: cannot connect to server: %s" % (label, e))
            s.close()
            return

        # Authenticate with shared secret
        if shared_secret:
            import struct
            auth_payload = (auth_magic +
                            struct.pack('B', len(shared_secret)) +
                            shared_secret)
            try:
                s.send(auth_payload)
                s.settimeout(auth_timeout)
                resp = s.recv(1)
                if not resp or resp != b'\x01':
                    self.logger.warn("%s: auth rejected by server", label)
                    s.close()
                    return
            except (socket.timeout, socket.error, OSError) as e:
                self.logger.warn("%s: auth failed: %s" % (label, e))
                s.close()
                return

            self.logger.info("%s: authenticated, relay active", label)

        s.setblocking(False)

        # Bidirectional relay: modem serial <-> TCP socket
        modem_tail = b""
        while True:
            had_data = False

            # Server -> Modem
            try:
                ready = select.select([s], [], [], 0)
                if ready[0]:
                    data = s.recv(4096)
                    if not data:
                        self.logger.info("%s: server closed connection", label)
                        break
                    self.modem._serial.write(data)
                    had_data = True
            except socket.error as e:
                err = e.args[0]
                if err == errno.EAGAIN or err == errno.EWOULDBLOCK:
                    pass
                else:
                    self.logger.warn("%s: TCP error: %s" % (label, e))
                    break

            # Modem -> Server
            waiting = self.modem._serial.in_waiting
            if waiting:
                data = self.modem._serial.read(waiting)
                if data:
                    had_data = True
                    # NO CARRIER detection (rolling tail buffer)
                    modem_tail = (modem_tail + data)[-32:]
                    if b"NO CARRIER" in modem_tail:
                        self.logger.info("%s: NO CARRIER detected", label)
                        break
                    try:
                        s.send(data)
                    except (socket.error, OSError):
                        self.logger.warn("%s: failed to send to server", label)
                        break

            # Carrier Detect pin check
            if not self.modem._serial.cd:
                time.sleep(2.0)
                if not self.modem._serial.cd:
                    self.logger.info("%s: Saturn hung up", label)
                    break

            if not had_data:
                time.sleep(0.01)

        s.close()
        self.logger.info("%s: disconnected", label)   
    # </Netlink Server Addition> 
    
    def modem_answer(self):
        try:
            self.modem.query_modem(b"ATA", timeout=30, response = "CONNECT")
        except IOError:
            return False
        return True
    
    def dcnet_connect(self):
        self.modem.stop_dial_tone()
        if self.modem_answer():
            time.sleep(3)
            self.logger.info("Call answered!")
            path = self.dcnet_path
            process = os.path.basename(path)
            cmd = [path, "-t", "{}".format(self.modem.device_name), "-b", "{}".format(self.modem.device_speed)]

            subprocess.Popen(cmd)
            
            time.sleep(3)
            while self.is_running(process):
                time.sleep(3)

            self.logger.info("Connection terminated")
            if self.modem._serial:
                self.modem._serial.close()
                # Give OS time to release
                time.sleep(2)
            self.modem._serial = None
            self.modem.connect()
            try:
                if self.modem._serial.in_waiting:
                    self.modem._serial.read(self.modem._serial.in_waiting)
            except Exception:
                pass
            self.modem.start_dial_tone()
            self.mode = "idle"
            time.sleep(5)
        else:
            self.reset()

    def is_running(self, process_name):
        try:
            output = subprocess.check_output(["pgrep", "-f", process_name])
            return bool(output.strip())
        except subprocess.CalledProcessError:
            return False
        
    def capcom(self):
        if self.osName != 'posix':
            return
        self.modem.stop_dial_tone()
        if self.modem_answer():
            self.logger.info("Call answered!")
            options = [
                "ktune",
                "noccp",
                "novj",
                "proxyarp",
                "lcp-echo-interval", "1",
                "lcp-echo-failure", "4",
                "lcp-max-terminate", "1",
                "lcp-restart", "1"
            ]
            self.pppd_run(device = self.modem._device, speed = self.modem._speed, options = options)
            self.modem.disconnect()
            from dcnow import DreamcastNowService
            dcnow = DreamcastNowService()
            dcnow.go_online("")
            for line in sh.tail("-f", "/var/log/messages", "-n", "1", _iter=True):
                if "pppd" in line and "Exit" in line:#wait for pppd to execute the ip-down script
                    self.logger.info("Detected modem hang up, going back to listening")
                    break
            dreampi.remove_alias_interface()
            dcnow.go_offline() #changed dcnow to wait 15 seconds for event instead of sleeping. Should be faster.
            self.mode = "idle"
            self.modem.connect()
            # If the ip-down was triggered by lcp echo failure, the modem often gets stuck in data mode. Fix that here. Harmless if modem isn't stuck.
            time.sleep(1.5)
            for i in range(3): # escape sequence
                self.modem._serial.write(b'+')
                time.sleep(0.2)
            time.sleep(1.5)
            self.modem.query_modem("ATH0")
            time.sleep(1)
            self.modem.start_dial_tone()
        else:
            self.modem.shake_it_off()
            self.reset()
        
    def pppd_run(self, device = None, speed = None, options = []):
        # self.logger.info([device, speed, options])
        if self.osName != 'posix':
            return
        tun_ip =  dreampi.get_ip_address("tun0")
        if tun_ip is not None:
            with open("/etc/ppp/options", "r") as f:
                for line in f:
                    if "ms-dns" in line:
                        self.dreamcast_ip = line.split(" ")[1].replace("\n", "")
            tun_ip_obj = ipaddress.IPv4Address(unicode(tun_ip,'utf-8'))
            self.tun_dc_ip = tun_ip_obj + 1
            tun_this_ip = self.tun_dc_ip + 1
            dreampi.create_alias_interface(self.dreamcast_ip, str(self.tun_dc_ip))
            
        else:
            with open("/etc/ppp/peers/dreamcast", "r") as f:
                for line in f:
                    if ":" in line:
                        self.dreamcast_ip = line.split(":")[1].replace("\n", "")
            self.tun_dc_ip = self.dreamcast_ip
            tun_this_ip = ipaddress.IPv4Address(unicode(self.dreamcast_ip,'utf-8')) + 1
        
        pppd_args = [
            "pppd",
            device, str(speed),
            str(tun_this_ip) + ":" + str(self.tun_dc_ip),
            "ms-dns", str(self.tun_dc_ip) if tun_ip is not None else str(tun_this_ip)
        ]

        pppd_args.extend(options)

        time.sleep(5)
        #  self.logger.info(pppd_args)

        self.logger.info(subprocess.check_output(pppd_args).decode())


    def poll(self):
        if time.time() - self.xband_timer > 900 and self.xband_listening:
            self.logger.info("Stop xband listening")
            self.close_xband()
        if self.usb:
            self.serial_poll()
        if self.mode == "idle":
            return 0
        elif self.mode == "PPP":
            return 0
        else:
            return self.mode_handler()

    def mode_handler(self):
        if self.mode == "netlink":
            self.do_netlink()
            self.reset()
        elif self.mode == "xband_matching":
            self.xband_match()
        elif self.mode == "xband_server":
            self.xband_server()
            self.xband_timer = time.time()
        elif self.mode == "xband_connect":
            if self.xband_init == False:
                self.xband_setup()
            self.init_xband()
            result = self.ring_phone()
            if result == "hangup":
                self.reset()
            else:
                self.netlink_exchange(state = "connected", opponent = (self.dial_string, 20001))
                self.reset()
        elif self.mode == "serial_ppp":
            self.serial_ppp()
        elif self.mode == "netlink_server":
            self.netlink_server()
            self.reset()
        elif self.mode == "dcnet":
            self.dcnet_connect()
        elif self.mode == "capcom":
            self.capcom()
        else:
            return 0
        return 0
    
