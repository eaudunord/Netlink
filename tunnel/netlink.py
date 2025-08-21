# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
#netlink_version=202507151230
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
try:
    import stun
except ImportError:
    os.system('pip install pystun3')
    import stun

pythonVer = platform.python_version_tuple()[0]
osName = os.name
if osName == 'posix':
    logger = logging.getLogger('dreampi')
else:
    logger = logging.getLogger('Netlink')
logger.setLevel(logging.INFO)

pinging = True

packetSplit = b"<packetSplit>"
dataSplit = b"<dataSplit>"
printout = False
if 'printout' in sys.argv:
    printout = True
timeout = 0.003
data = []
state = "starting"
poll_rate = 0.01
ser = ""
matching = True

def digit_parser(modem):
    char = modem._serial.read(1).decode() #first character was <DLE>, what's next?
    tel_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9']
    ip_digits = ['0','1', '2', '3', '4', '5', '6', '7', '8', '9','*']
    if char in tel_digits:
        dial_string = char
        last_heard = time.time()
        while(True):
            if time.time() - last_heard > 3: #if more than 3 seconds of silence, assume done dialing.
                break
            char = modem._serial.read(1).decode()
            if not char:
                continue
            if ord(char) == 16:
                try:
                    char = modem._serial.read(1).decode()
                    digit = int(char) #will raise exception if anything but a digit
                    dial_string+= str(digit)
                    last_heard = time.time()
                except (TypeError, ValueError):
                    pass
        #at this point we have the full dialed string. We can insert an IP address lookup here. For now, assume PPP
        if dial_string == "0":
            return {'client':'direct_dial','dial_string':dial_string,'side':'waiting'}
        if dial_string == "70":
            logger.info("Call waiting disabled")
            return "nada"
        else:
            return {'client':'ppp_internet','dial_string':dial_string,'side':'na'}

    elif char == '#':
        dial_string = ""
        last_heard = time.time()
        while (True):
            if time.time() - last_heard > 3: #if more than 3 seconds of silence, assume done dialing.
                break
            char = modem._serial.read(1).decode() #modem sends <DLE>s at regular intervals to indicate silence
            if not char:
                continue
            if ord(char) == 16: #16 is <DLE>
                try:
                    char = modem._serial.read(1).decode()
                    if char == '#':
                        if '*' in dial_string: #if the ip address was dialed with * no need for further formatting
                            break
                        elif len(dial_string) >= 12: #if we have a full 12 digit string add in '.' every three characters
                            dial_string = '.'.join(dial_string[i:i+3] for i in range(0, len(dial_string), 3))
                            break
                    if char in ip_digits:
                        dial_string += char
                        last_heard = time.time()
                except (TypeError, ValueError):#Dreampi originally tried to convert characters to int and passed on the exception raised for other characters. This shouldn't be needed anymore.
                    pass
        if len(dial_string) == 3 and dial_string[0] == "0": # This condition indicates a game is waiting for a call
            return {'client':'direct_dial','dial_string':dial_string,'side':'waiting'}
        else:
            return {'client':'direct_dial','dial_string':dial_string,'side':'calling'}
    else:
        return "nada"

def initConnection(ms,dial_string):
    global matching
    opponent = dial_string.replace('*','.')
    ip_set = opponent.split('.')
    for i,set in enumerate(ip_set): #socket connect doesn't like leading zeroes now
        fixed = str(int(set))
        ip_set[i] = fixed
    opponent = ('.').join(ip_set)
    registered = False

    if ms == "waiting":
        logger.info("I'm waiting")
        registered = False
        timerStart = time.time()
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(120)
        tcp.bind(('', PORT))
        tcp.listen(5)
        while True:
            if time.time() - timerStart > 120:
                if len(dial_string) == 3 and registered:
                    timed_out(dial_string[-2:], my_ip)
                return ["failed", None]
            ready = select.select([tcp], [], [],0)
            if ready[0]:
                conn, addr = tcp.accept()
                opponent = addr[0]
                logger.info('Connection from %s' % opponent)
                while True:
                    try:
                        data = conn.recv(1024)
                    except socket.error: #first try can return no payload
                        continue
                    if data == b'readyip':
                        conn.sendall(b'g2gip')
                        logger.info("Sending Ring")
                        ser.write(("RING\r\n").encode())
                        ser.write(("CONNECT\r\n").encode())
                        logger.info("Ready for Data Exchange!")
                        #tcp.shutdown(socket.SHUT_RDWR) #best practice is to close your socket, but it gives me issues.
                        #tcp.close()
                        if registered:
                            timed_out(dial_string[-2:], my_ip)
                        return ["connected", (opponent, 20002)]
                    if not data:
                        logger.info("Failed to init")
                        #tcp.shutdown(socket.SHUT_RDWR)
                        #tcp.close()
                        break
            if len(dial_string) == 3: # matchmaking is on by default
                if matching:
                    my_ip, ext_port = getWanIP(20001) # doing this every loop is intentional. Acts as an NAT keep-alive.
                    if my_ip:
                        if not registered:
                            if register(dial_string[-2:], my_ip, ext_port):
                                registered = True
                        elif registered:
                            status, opponent = get_status(dial_string[-2:], my_ip)
                            if status:
                                logger.info("Sending Ring")
                                ser.write(("RING\r\n").encode())
                                ser.write(("CONNECT\r\n").encode())
                                logger.info("Ready for Data Exchange!")
                                return ["connected",opponent]
                    else:
                        logger.info("Couldn't get WAN information. Won't register for match. Trying again in 3 seconds")
                    time.sleep(3)


    if ms == "calling":
        logger.info("I'm calling")
        if len(dial_string) > 3: # treat the call as a direct dial attempt
            PORT = 65432
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp.settimeout(120)
            try:
                tcp.connect((opponent, PORT))
                tcp.sendall(b"readyip")
                ready = select.select([tcp], [], [])
                if ready[0]:
                    data = tcp.recv(1024)
                    if data == b'g2gip':
                        logger.info("Ready for Data Exchange!")
                        #tcp.shutdown(socket.SHUT_RDWR)
                        #tcp.close()
                        return ["connected", (opponent, 20001)]
            except socket.error:
                return ["failed", ""]
        else:
            if dial_string == "999":
                matching = False
                logger.info("Matchmaking disabled")
                return ["failed", None]
            elif dial_string == "888":
                matching = True
                logger.info("Matchmaking enabled")
                return ["failed", None]
            else: # connect to the matchmaking server and get a match
                my_ip, ext_port = getWanIP(20002)
                if my_ip:
                    status, opponent = get_match(dial_string[-2:], my_ip, ext_port)
                    if status:
                        return ["connected", opponent]
                    else:
                        return ["failed", None]
                else:
                    return ["failed", None]
                         
    else:
        return ["failed", None]


def register(game_id, ip_address, port):
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
        logger.info("Registered for a match")
        return True
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
        logger.info("Couldn't connect to matching server")
        logger.info(e)
        return False
    
def get_status(game_id, ip_address):
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
        logger.info("Couldn't connect to matching server")
        return [False, (None, None)]

def get_match(game_id, ip_address, port):
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
        logger.info(status)
        if status == "found opponent":
            dial_string = r.json()["opponent ip_address"]
            address, oppPort = dial_string
            oppPort = int(oppPort)
            opponent = '.'.join(str(int(address[i:i+3])) for i in range(0, len(address), 3))
            return [True, (opponent, oppPort)]
        else:
            return [False, (None, None)]
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError) as e:
        logger.info("Couldn't connect to matching server")
        logger.info(e)
        return [False, (None, None)]

def timed_out(game_id, ip_address):
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
        logger.info("Wait timed out. Deregistered from matching server")
    except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError):
        logger.info("Couldn't connect to matching server")
        return False, None

def getWanIP(port):
    try:
        nat_type, external_ip, external_port = stun.get_ip_info(source_port=port, stun_host="stun2.l.google.com", stun_port=19302)
        external_ip = "".join([x.zfill(3) for x in external_ip.split(".")])
    except AttributeError:
        logger.info("Couldn't get WAN information")
        return None, None
    return external_ip, external_port


def netlink_setup(side,dial_string,modem):
    global ser
    ser = modem._serial
    state = initConnection(side,dial_string)
    return state

def netlink_exchange(side,net_state,opponent,ser=ser):
    def listener():
        logger.info(state)
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
        while(state != "netlink_disconnected"):
            ready = select.select([udp],[],[],0) #polling select
            if ready[0]:
                packetSet, remote = udp.recvfrom(1024)
                
                #start pinging code block
                if pinging == True:
                    pingCount +=1
                    if pingCount >= 30:
                        pingCount = 0
                        ping = time.time()
                        udp.sendto(b'PING_SHIRO', opponent)
                    if packetSet == b'PING_SHIRO':
                        udp.sendto(b'PONG_SHIRO', opponent)
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
                        if osName != 'posix':
                            sys.stdout.write('Ping: %s Max: %s | Jitter: %s Max: %s | Avg Ping: %s |  Avg Jitter: %s | Recovered Packets: %s         \r' % (pingResult,maxPing,jitter, maxJitter,pingAvg,jitterAvg,recoveredCount))
                        lastPing = pingResult
                        continue
                #end pinging code block

                packets= packetSet.split(packetSplit)
                try:
                    while True:
                        packetNum = 0
                        
                        #go through all packets 
                        for p in packets:
                          if int(p.split(dataSplit)[1]) == currentSequence:
                            break
                          packetNum += 1
                        
                        #if the packet needed is not here,  grab the latest in the set
                        if packetNum == len(packets):
                            packetNum = 0
                        if packetNum > 0 :
                            recoveredCount += 1
                        message = packets[packetNum]
                        payload = message.split(dataSplit)[0]
                        sequence = message.split(dataSplit)[1]
                        if int(sequence) < currentSequence:
                            break  #All packets are old data, so drop it entirely
                        
                        currentSequence = int(sequence) + 1
                        
                        toSend = payload
                        
                        ser.write(toSend)
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except IndexError:
                    continue
                    
        logger.info("Listener stopped")        
                
    def sender(side,opponent):
        global state
        logger.info("Sending")
        sequence = 0
        packets = []
        ser.timeout = None
        
        while(state != "netlink_disconnected"):
            new = ser.read(1) #should now block until data. Attempt to reduce CPU usage.
            raw_input = new + ser.read(ser.in_waiting)
            if b"NO CARRIER" in raw_input:
                print('')
                logger.info("NO CARRIER")
                state = "netlink_disconnected"
                time.sleep(1)
                udp.close()
                logger.info("Sender stopped")
                return
            
            try:
                payload = raw_input
                seq = str(sequence)
                if len(payload)>0:
                    
                    packets.insert(0,(payload+dataSplit+seq.encode()))
                    if(len(packets) > 5):
                        packets.pop()
                        
                    for i in range(2): #send the data twice. May help with drops or latency    
                        ready = select.select([],[udp],[]) #blocking select  
                        if ready[1]:
                            udp.sendto(packetSplit.join(packets), opponent)
                                
                    sequence+=1
            except:
                continue

    global state 
    state = net_state              
    if state == "connected":
        t1 = threading.Thread(target=listener)
        t2 = threading.Thread(target=sender,args=(side,opponent))
        if side == "waiting": #we're going to bind to a port. Some users may want to run two instances on one machine, so use different ports for waiting, calling
            Port = 20001
        if side == "calling":
            Port = 20002
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 184)
        udp.setblocking(0)
        udp.bind(('', Port))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()

def kddi_exchange(side,net_state,opponent,ser=ser):
    def listener():
        logger.info(state)
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
        firstRun = True
        lastWrite = None
        if side == "waiting":
            oppPort = 20002
        if side == "calling":
            oppPort = 20001
        while(state != "netlink_disconnected"):
            ready = select.select([udp],[],[],0) #polling select
            if ready[0]:
                packetSet = udp.recv(1024)
                
                #start pinging code block
                if pinging == True:
                    pingCount +=1
                    if pingCount >= 30:
                        pingCount = 0
                        ping = time.time()
                        udp.sendto(b'PING_SHIRO', (opponent,oppPort))
                    if packetSet == b'PING_SHIRO':
                        udp.sendto(b'PONG_SHIRO', (opponent,oppPort))
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
                        if osName != 'posix':
                            sys.stdout.write('Ping: %s Max: %s | Jitter: %s Max: %s | Avg Ping: %s |  Avg Jitter: %s | Recovered Packets: %s         \r' % (pingResult,maxPing,jitter, maxJitter,pingAvg,jitterAvg,recoveredCount))
                        lastPing = pingResult
                        continue
                #end pinging code block

                packets= packetSet.split(packetSplit)
                try:
                    while True:
                        packetNum = 0
                        
                        #go through all packets 
                        for p in packets:
                          if int(p.split(dataSplit)[1]) == currentSequence:
                            break
                          packetNum += 1
                        
                        #if the packet needed is not here,  grab the latest in the set
                        if packetNum == len(packets):
                            packetNum = 0
                        if packetNum > 0 :
                            recoveredCount += 1
                        message = packets[packetNum]
                        payload = message.split(dataSplit)[0]
                        sequence = message.split(dataSplit)[1]
                        if int(sequence) < currentSequence:
                            break  #All packets are old data, so drop it entirely
                        
                        currentSequence = int(sequence) + 1
                        
                        toSend = payload

                        if firstRun == True:
                            if pythonVer == '2':
                                lastWrite = time.clock()
                                firstRun = False
                            else:
                                lastWrite = time.perf_counter()
                                firstRun = False
                        elif firstRun == False:
                            if pythonVer == '2':
                                if time.clock() - lastWrite > 0.026:
                                    logger.info('Late KDDI Packet')
                                lastWrite = time.clock()
                            else:
                                if time.perf_counter() - lastWrite > 0.026:
                                    logger.info('Late KDDI Packet')
                                lastWrite = time.perf_counter()

                        ser.write(toSend)
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except IndexError:
                    continue
                    
        logger.info("Listener stopped")        
                
    def sender(side,opponent):
        global state
        logger.info("Sending")
        first_run = False
        if side == "waiting":
            oppPort = 20002
        if side == "calling":
            oppPort = 20001
        last = 0
        sequence = 0
        packets = []
        ser.timeout = 0.5
        
        while(state != "netlink_disconnected"):
            if not ser.cd:
                print('')
                logger.info("NO CARRIER")
                ser.read(ser.in_waiting)
                state = "netlink_disconnected"
                time.sleep(1)
                udp.close()
                logger.info("Sender stopped")
                return
            raw_input = b''
            new = ser.read(1)
            if len(new) == 0:
                continue
            else:
                raw_input += new
            while len(raw_input) < 6:
                new = ser.read(1)
                if new == b'\x0a' or len(new) == 0:
                    raw_input += new
                    break
                raw_input += new
                
            
            try:
                payload = raw_input
                seq = str(sequence)
                if len(payload)>0:
                    
                    packets.insert(0,(payload+dataSplit+seq.encode()))
                    if(len(packets) > 5):
                        packets.pop()
                        
                    for i in range(2): #send the data twice. May help with drops or latency    
                        ready = select.select([],[udp],[]) #blocking select  
                        if ready[1]:
                            udp.sendto(packetSplit.join(packets), (opponent,oppPort))
                                
                    sequence+=1
            except:
                continue

    global state 
    state = net_state              
    if state == "connected":
        t1 = threading.Thread(target=listener)
        t2 = threading.Thread(target=sender,args=(side,opponent))
        if side == "waiting": #we're going to bind to a port. Some users may want to run two instances on one machine, so use different ports for waiting, calling
            Port = 20001
        if side == "calling":
            Port = 20002
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 184)
        udp.setblocking(0)
        udp.bind(('', Port))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        


