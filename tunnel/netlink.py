# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
#netlink_version=202508311113
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
    if osName == 'posix':
        logger = logging.getLogger('dreampi')
    else:
        logger = logging.getLogger('Netlink')
    if osName == 'posix': # should work on linux and Mac for USB modem, but untested.
        femtoSipPath = "/home/pi/dreampi/femtosip"
    else:
        femtoSipPath = os.path.realpath('./')+"/femtosip"
    logger.setLevel(logging.INFO)
    packetSplit = b"<packetSplit>"
    dataSplit = b"<dataSplit>"
    timeout = 0.003

    def __init__(self, modem):
        self.modem = modem
        self.pinging = True
        self.printout = False
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
        self.usb = None
        # check for serial port on linux
        if self.osName == 'posix':
            try:
                self.usb = serial.Serial("/dev/ttyUSB0", baudrate=self.usb_baud, rtscts=True)
                self.usb.timeout = 0.01
                self.logger.info("USB-Serial adapter found!")
            except:
                self.logger.info("No USB-Serial adapter detected")
                self.usb = None


    def digit_parser(self):
        last_heard = time.time()
        raw_string = ""
        tel_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '#']
        char = self.modem._serial.read(1).decode()
        if char in tel_digits:
            raw_string += char
            while True:
                if time.time() - last_heard > 3:
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
        if raw_string == "0":
            self.ms = "waiting"
            self.mode = "netlink"
            self.dial_string = raw_string
            return {'client':self.mode,'dial_string':raw_string}
        elif raw_string == "*70":
            self.logger.info("Call waiting disabled")
            self.mode = "idle"
            self.dial_string = ""
            return {'client':self.mode, 'dial_string':raw_string}
        elif raw_string in ["18002071194","19209492263","0120717360","0355703001"]:
            self.mode = "xband_server"
            self.dial_string = ""
            return {'client':self.mode, 'dial_string':raw_string}
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
                return {'client':self.mode,'dial_string':raw_string}             
        else:
            if len(raw_string) > 0: # any sequence that we don't recognize, assume is meant to be PPP
                self.ms = None
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
                    self.logger.info('Connection from %s' % opponent)
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
                        my_ip, ext_port = self.getWanIP(20001)
                        if my_ip and ext_port: # only update if the function returns good info
                            self.my_ip = my_ip
                            self.ext_port = ext_port # doing this every loop is intentional. Acts as an NAT keep-alive.
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
                            self.logger.info("Couldn't get WAN information. Won't register for match. Trying again in 3 seconds")
                        time.sleep(3)


        if self.ms == "calling":
            self.logger.info("Calling")
            if len(self.dial_string) > 3: # treat the call as a direct dial attempt
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
                    return ["failed", ""]
            else:
                if self.dial_string == "999":
                    self.matching = False
                    self.logger.info("Matchmaking disabled")
                    result = ["failed", None]
                elif self.dial_string == "888":
                    self.matching = True
                    self.logger.info("Matchmaking enabled")
                    result = ["failed", None]
                else: # connect to the matchmaking server and get a match
                    my_ip, ext_port = self.getWanIP(20002)
                    if my_ip and ext_port: # only update if the function returns good data
                        self.my_ip = my_ip
                        self.ext_port = ext_port
                    if self.my_ip:
                        status, opponent = self.get_match(self.dial_string[-2:], self.my_ip, self.ext_port)
                        if status:
                            result = ["connected", opponent]
                        else:
                            result = ["failed", None]
                    else:
                        result = ["failed", None]
                            
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
        self.logger.info(self.state)
        pingCount = 0
        lastPing = 0
        ping = time.time()
        pong = time.time()
        jitterStore = []
        pingStore = []
        currentSequence = 0
        maxPing = 0
        maxJitter = 0
        recoveredCount = 0
        while(self.state != "netlink_disconnected"):
            ready = select.select([self.udp],[],[],0) #polling select
            if ready[0]:
                packetSet, remote = self.udp.recvfrom(1024)
                
                #start pinging code block
                if self.pinging == True:
                    pingCount +=1
                    if pingCount >= 30:
                        pingCount = 0
                        ping = time.time()
                        self.udp.sendto(b'PING_SHIRO', opponent)
                    if packetSet == b'PING_SHIRO':
                        self.udp.sendto(b'PONG_SHIRO', opponent)
                        continue
                    elif packetSet == b'PONG_SHIRO':
                        pong = time.time()
                        pingResult = round((pong-ping)*1000,2)
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
                        lastPing = pingResult
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
                        
                        self.modem._serial.write(toSend)
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except IndexError:
                    continue
        self.close_udp()            
        self.logger.info("Listener stopped")        
                    
    def sender(self, opponent):
        first_run = True
        self.logger.info("Sending")
        sequence = 0
        packets = []
        self.modem._serial.timeout = None
        if first_run:
            if select.select([],[self.udp],[],0)[1]:
                self.udp.sendto(b'OPEN_SHIRO', opponent)
            first_run = False
        
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
                            self.udp.sendto(self.packetSplit.join(packets), opponent)
                                
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
            
            t1.start()
            t2.start()
            t1.join()
            t2.join()

    def do_netlink(self):
        self.modem.stop_dial_tone()
        self.close_udp()
        try:
            self.modem.connect_netlink(speed=57600,timeout=0.01,rtscts = True) #non-blocking version
            self.modem.query_modem(b'AT\x25E0\V1')
            self.modem.query_modem(b'AT\x25C0\N3')
            # self.modem.query_modem(b'AT+MS=V32b,1,14400,14400,14400,14400') probably not necessary to be so explicit with rates and modulation
            self.modem.query_modem(b"ATA", timeout=30, response = "CONNECT")
        except IOError:
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
        try:
            self.modem.query_modem("ATA", timeout=30, response = "CONNECT")
        except IOError:
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
            return
        if time.time() - self.xband_timer > 900:
            self.mode = "idle"
            self.close_xband()
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
            except requests.exceptions.HTTPError:
                self.logger.info("unable to fetch femtosip")
                return "dropped"
            except OSError:
                self.logger.info("error creating femtosip directory")
        else:
            self.xband_init = True
        

    def open_xband(self):
        if not self.xband_sock:
            PORT = 65433
            self.xband_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.xband_sock.setblocking(0)
            self.xband_sock.bind(('', PORT))
            self.xband_sock.listen(5)
        self.xband_listening = True

    def close_xband(self):
        try:
            if self.xband_sock:
                self.xband_sock.close()
                time.sleep(2)
                self.xband_sock = None
            self.xband_listening = False
        except:
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
                            self.modem.query_modem("ATX1D", timeout=30, response = "CONNECT")
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
                    if time.time() - callTime > 120:
                        break
        return result
    
    def init_xband(self):
        self.modem.stop_dial_tone()
        self.modem.connect_netlink(speed=57600,timeout=0.05,rtscts=True)
        self.modem.query_modem(b'AT\x25E0')
        self.modem.query_modem(b"AT\V1\x25C0")
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
                        self.modem.query_modem("ATA", timeout=30, response = "CONNECT")
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
        return result

    def reset(self):
        self.modem.connect()
        self.modem.start_dial_tone()
        self.mode = "idle"
        self.state = "starting"

    def serial_poll(self):
        if self.usb:
            try:
                payload = self.usb.read(self.usb.in_waiting)
                if len(payload) > 0:
                    self.logger.info("serial port: %s" % payload)
                    if payload[:2] == b'AT':
                        if payload == b'AT\r\n' or payload == b'AT\n':
                            self.usb.write(b'OK\r\n')
                        elif payload == b'ATZ\r\n' or payload == b'ATZ\n':
                            self.usb.write(b'OK\r\n')
                        elif payload[:4] == b'ATDT':
                            self.usb.write(b'CONNECT 115200\r\n')
                            time.sleep(5) #some games need a sleep before turning on pppd
                            self.logger.info("Call answered!")
                            # os.system("pon -detach crtscts lcp-echo-interval 10 lcp-echo-failure 2 lock local proxyarp {}:{} /dev/ttyUSB0 115200".format(this_ip,dreamcast_ip))
                            self.logger.info(subprocess.check_output(["pon", "dreamcast", "lcp-echo-interval", "10", "local", "crtscts", "lcp-echo-failure","2","lcp-max-terminate","1","/dev/ttyUSB0", "115200"]).decode())
                            self.logger.info("CONNECT")
                            self.mode = "serial_ppp"
                            if self.usb and self.usb.is_open:
                                self.usb.flush() #added a flush, is data hanging on in the buffer?
                                self.usb.close()
                                self.usb = None
                            self.modem.stop_dial_tone()
                        else:
                            self.usb.write(b'OK\r\n')
            except IOError:
                self.logger.info("serial device disconnected")
                self.usb = None
        else:
            return 0
        
    def serial_ppp(self):
        with open("/etc/ppp/options", "r") as f:
            for line in f:
                if "ms-dns" in line:
                    dreamcast_ip = line.split(" ")[1].replace("\n", "")
        tun_ip =  dreampi.get_ip_address("tun0")
        if tun_ip is not None:
            tun_ip_obj = ipaddress.IPv4Address(unicode(tun_ip,'utf-8'))
            tun_dc_ip = tun_ip_obj + 1
            dreampi.create_alias_interface(dreamcast_ip, str(tun_dc_ip))
        from dcnow import DreamcastNowService
        dcnow = DreamcastNowService()
        dcnow.go_online(dreamcast_ip)

            
        for line in sh.tail("-f", "/var/log/messages", "-n", "1", _iter=True):
            if "pppd" in line and "Exit" in line:#wait for pppd to execute the ip-down script
                self.logger.info("Detected modem hang up, going back to listening")
                break
            if "pppd" in line and "Connection terminated." in line:
                self.logger.info("pppd ip-down finished")
                try:
                    print(subprocess.check_output(['sudo', 'poff', '-a']))
                    time.sleep(5)
                    print(subprocess.check_output(['sudo', 'poff', '-a']))
                    # why do I have to do this twice? pppd doesn't detect a hangup when ppp disconnects.
                    # a cleaner solution would be preferable but this works
                except Exception as e:
                    print(e)
        dreampi.remove_alias_interface()
        dcnow.go_offline() #changed dcnow to wait 15 seconds for event instead of sleeping. Should be faster.
        self.mode = "idle"
        self.modem.connect()
        self.modem.start_dial_tone()
        # modem = Modem(device_and_speed[0], device_and_speed[1], dial_tone_enabled)
        try:
            self.usb = serial.Serial("/dev/ttyUSB0", baudrate=self.usb_baud, rtscts=True)
            self.usb.timeout = 0.01
        except:
            self.logger.info("No USB-Serial adapter detected")
            self.usb = None
        self.logger.info('Reset serial port')

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
        else:
            return 0
        return 0


        


