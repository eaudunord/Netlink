# -*- coding: utf-8 -*-
"""
Created on Thu May 19 08:01:31 2022

@author: joe
"""
#netlink_version=1663872260.57
from subprocess import CalledProcessError
import sys

if __name__ == "__main__":
    print("This script should not be run on its own")
    sys.exit()

import socket
import time
import datetime
import serial
from datetime import datetime
import logging
logger = logging.getLogger('netlink')
import threading
import binascii
import select

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
        while (True):
            char = modem._serial.read(1).decode() #this is blocking, but the modem sends <DLE>s at regular intervals to indicate silence
            if not char: #which makes this pointless
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
                except (TypeError, ValueError):#Dreampi originally tried to convert characters to int and passed on the exception raised for other characters. This shouldn't be needed anymore.
                    pass
        return {'client':'direct_dial','dial_string':dial_string,'side':'calling'}
    else:
        return "nada"

def initConnection(ms,dial_string):
    opponent = dial_string.replace('*','.')
    ip_set = opponent.split('.')
    for i,set in enumerate(ip_set): #socket connect doesn't like leading zeroes now
        fixed = str(int(set))
        ip_set[i] = fixed
    opponent = ('.').join(ip_set)

    if ms == "waiting":
        logger.info("I'm waiting")
        print(datetime.now())
        timerStart = time.time()
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(120)
        tcp.bind(('', PORT))
        tcp.listen(5)
        while True:
            if time.time() - timerStart > 120:
                return ["failed",""]
            ready = select.select([tcp], [], [],0)
            if ready[0]:
                conn, addr = tcp.accept()
                opponent = addr[0]
                logger.info('connection from %s' % opponent)
                while True:
                    try:
                        data = conn.recv(1024)
                    except socket.error: #first try can return no payload
                        continue
                    if data == b'readyip':
                        print(datetime.now(),"received handshake initiation")
                        conn.sendall(b'g2gip')
                        print(datetime.now(),"sent handshake acknowledge")
                        if dial_string != "000":
                            logger.info("Sending Ring")
                            ser.write(("RING\r\n").encode())
                            ser.write(("CONNECT\r\n").encode())
                        logger.info("Ready for Data Exchange!")
                        #tcp.shutdown(socket.SHUT_RDWR) #best practice is to close your socket, but it gives me issues.
                        #tcp.close()
                        return ["connected",opponent]
                    if not data:
                        print("failed to init")
                        #tcp.shutdown(socket.SHUT_RDWR)
                        #tcp.close()
                        break

    if ms == "calling":
        print(datetime.now(),"I'm calling")
        PORT = 65432
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp.settimeout(15)
        try:
            tcp.connect((opponent, PORT))
            tcp.sendall(b"readyip")
            print(datetime.now(),"started handshake")
            ready = select.select([tcp], [], []) #blocking wait
            if ready[0]:
                print(datetime.now(),"waiting to receive handshake response")
                now = time.time()
                while True:
                    try:
                        data = tcp.recv(1024)
                    except socket.error: #first try can return no payload
                        if time.time() - now > 15:
                            print("failed with timeout")
                            return ["failed", ""]
                        continue
                    print(datetime.now(),"received a response")
                    # print(data)
                    if data == b'g2gip':
                        logger.info("Ready for Data Exchange!")
                        #tcp.shutdown(socket.SHUT_RDWR)
                        #tcp.close()
                        return ["connected",opponent]
        except socket.error:
            print("failed")
            return ["failed", ""]
                
    else:
        return ["error","error"]




            

         


def netlink_setup(side,dial_string,modem):
    global ser
    ser = modem._serial
    state = initConnection(side,dial_string)
    #time.sleep(0.2)
    return state

def netlink_exchange(side,net_state,opponent,ser=ser):
    def listener():
        print(state)
        last = 0
        currentSequence = 0
        # #logging block
        # f = open("recv-output.txt", "a")
        # f.write("New output")
        # f.write("\n")
        # ts = round(time.time() * 10000)
        # lastTime = round(time.time() * 10000) - ts
        # #logging block

        while(state != "netlink_disconnected"):
            ready = select.select([udp],[],[],0) #polling select
            if ready[0]:
                # #logging block
                # currentTime = round(time.time() * 10000) - ts
                # f.write(str(currentTime))
                # f.write("\t")
                # f.write(str(max(currentTime - lastTime,0)))
                # f.write("\t")
                # #logging block

                packetSet = udp.recv(1024)

                # #logging block
                # currentTime = round(time.time() * 10000) - ts            
                # f.write(str(currentTime))
                # f.write("\t")
                # f.write(str(max(currentTime - lastTime,0)))
                # f.write("\t")
                # #logging block

                packets= packetSet.split(packetSplit)
                
                # #logging block
                # lastTime = currentTime
                # for p in packets:
                #     f.write(p.split(dataSplit)[1])
                #     f.write("-")          
                #     f.write(binascii.hexlify( p.split(dataSplit)[0] ))
                #     f.write("\t")        
                # f.write("\n")                        
                # #logging block

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
                        
                        message = packets[packetNum]
                        payload = message.split(dataSplit)[0]
                        sequence = message.split(dataSplit)[1]
                        if int(sequence) < currentSequence:
                            break  #All packets are old data, so drop it entirely
                        
                        currentSequence = int(sequence) + 1
                        
                        toSend = payload

                        # print("received:",toSend)

                        ser.write(toSend)
                        if len(payload) > 0 and printout == True:
                            logger.info(binascii.hexlify(payload))
                        if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                            break

                except IndexError:
                    continue
                    
        logger.info("listener stopped")  
        # f.close()    #logging  
                
    def sender(side,opponent):
        global state
        print(datetime.now(),"sending")
        first_run = True
        if side == "waiting":
            oppPort = 20002
        if side == "calling":
            oppPort = 20001
        last = 0
        sequence = 0
        print(opponent,oppPort)

        # #logging block
        # f = open("send-output.txt", "a")
        # f.write("New output")
        # f.write("\n")
        # ts = round(time.time() * 10000)
        # lastTime = round(time.time() * 10000) - ts
        # #logging block

        packets = []
        ser.timeout = None
        while(state != "netlink_disconnected"):
            new = ser.read(1) #should now block until data. Attempt to reduce CPU usage.
            
            raw_input = new + ser.read(ser.in_waiting)

            if b"NO CARRIER" in raw_input:
                print(datetime.now(),"NO CARRIER")
                state = "netlink_disconnected"
                time.sleep(1)
                udp.close()
                logger.info("sender stopped")
                # f.close() #logging
                return
                
            # print(datetime.now(),"sent:", raw_input)
            
            try:
                payload = raw_input
                seq = str(sequence)
                if len(payload)>0:
                    
                    packets.insert(0,(payload+dataSplit+seq.encode()))
                    if(len(packets) > 5):
                        packets.pop()
                    # #logging block
                    # currentTime = round(time.time() * 10000) - ts        
                    # f.write(str(currentTime))
                    # f.write("\t")
                    # f.write(str(max(currentTime - lastTime,0)))
                    # f.write("\t")
                    # lastTime = currentTime
                    # #logging block
                    for i in range(2): #send the data twice. May help with drops or latency    
                        ready = select.select([],[udp],[]) #blocking select  
                        if ready[1]:
                            udp.sendto(packetSplit.join(packets), (opponent,oppPort))
                        #     #logging block
                        #     f.write("Success")
                        # else:
                        #     f.write("Dropped") 
                        # currentTime = round(time.time() * 10000) - ts
                        # f.write("\t")
                        # f.write(str(currentTime))
                        # f.write("\t")
                        # f.write(str(max(currentTime - lastTime,0)))
                       
                        # lastTime = currentTime
                       
                        # for p in packets:
                        #     f.write(p.split(dataSplit)[1])
                        #     f.write("-")          
                        #     f.write(binascii.hexlify( p.split(dataSplit)[0] ))
                        #     f.write("\t")   
                       
                        
                        # f.write("\n")       
                        #  #logging block     
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
        udp.setblocking(0)
        udp.bind(('', Port))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        


