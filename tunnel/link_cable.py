import socket
import time
import serial
import select
import sys
import threading
from modemClass import Modem
import logging
import os

osName = os.name
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('Tunnel')
logger.setLevel(logging.INFO)
pinging = True
printout = False
packetSplit = b"<packetSplit>"
dataSplit = b"<dataSplit>"
com_port = None
speed = None
ms = None
dial_string = None
ping = time.time()

if sys.version_info < (3,0,0):
    input = raw_input

def setup(com_port = com_port, speed = speed, ms = ms, dial_string = dial_string):
    for arg in sys.argv[1:]:
        if len(arg.split("=")[1].strip()) == 0:
            continue
        elif arg.split("=")[0] == "com":
            com_port = arg.split("=")[1].strip()
        elif arg.split("=")[0] == "speed":
            speed = int(arg.split("=")[1].strip())
        elif arg.split("=")[0] == "state":
            ms = arg.split("=")[1].strip()
        elif arg.split("=")[0] == "address":
            dial_string = arg.split("=")[1].strip()
                            
    while True:
        if not com_port:
            com_port = input("\nCOM port: ")
        try:
            testCon = serial.Serial(com_port,9600)
            testCon.close()
            break
        except serial.SerialException:
            print("Invalid COM port")
            com_port = None
            continue
    print("\nUsing %s" % com_port)

    while True:
        if speed:
            break
        speed = input("\nGame:\r\n[1] Aero Dancing F\r\n[2] Aero Dancing I\r\n[3] F355\r\n[4] Sega Tetris\r\n[5] Virtual On\r\n[6] Hell Gate\r\n[7] custom\r\n[8] calculated\r\n"
            )
        if speed == '1':
            speed = 28800
        elif speed == '2':
            speed = 38400
        elif speed == '3':
            speed = 230400
        elif speed == '4':
            speed = 14400
        elif speed == '5':
            speed = 260416
        elif speed == '6':
            speed = 57600
        elif speed == '7':
            try:
                int(speed)
                speed = int(input("\ncustom baud: "))
            except ValueError:
                print("Invalid selection")
                speed = None
                continue
        elif speed == '8':
            try:
                int(speed)
                multiplier = int(input("\nSCBRR2 multiplier: "))
                speed = int(round((50*1000000)/(multiplier+1)/32,0))
                print(speed)
            except ValueError:
                print("Invalid selection")
                speed = None
                continue
        else:
            print("invalid selection")
            speed = None
            continue

    while True:
        if ms:
            break
        side = input('\nWait or connect:\n[1] Wait\n[2] Connect\n')
        if side == '1' or side =='2':
            if side == '1':
                ms = "waiting"
            else:
                ms = "calling"
        else:
            print('Invalid selection')
            ms = None
            continue

    if not dial_string:
        dial_string = input("Opponent IP address: ")

    modem = Modem(com_port, speed,send_dial_tone=False)
    modem.connect_netlink(speed=speed,rtscts=True)
    print("setting serial rate to: %s" % speed)
    ser = modem._serial
    ser.reset_output_buffer() #flush the serial output buffer. It should be empty, but doesn't hurt.
    ser.reset_input_buffer()
    ser.timeout = None
    variables = (
        com_port,
        speed,
        ms,
        dial_string,
        modem,
        ser
    )
    return variables

def initConnection(ms,dial_string):
    if dial_string:
        opponent = dial_string.replace('*','.')
        ip_set = opponent.split('.')
        for i,set in enumerate(ip_set): #socket connect doesn't like leading zeroes now
            fixed = str(int(set))
            ip_set[i] = fixed
        opponent = ('.').join(ip_set)

    return ("connecting",opponent)



def serial_exchange(side,state,opponent):
    
    def listener():
        global ser
        global ping
        global state
        first_run = True
        lastPing = 0
        pong = time.time()
        startup = time.time()
        jitterStore = []
        pingStore = []
        currentSequence = 0
        maxPing = 0
        maxJitter = 0
        recoveredCount = 0
        if side == "waiting":
            oppPort = 21002

        if side == "calling":
            oppPort = 21001
        while(state != "netlink_disconnected"):
            ready = select.select([udp],[],[],0) #polling select
            if ready[0]:
                try:
                    packetSet = udp.recv(1024)
                    while time.time() - startup < 3:
                        # Discard packets for 3 seconds in case there are any in the OS buffer.
                        continue
                    #start pinging code block
                    if pinging == True:
                        if packetSet == b'PING_SHIRO':
                            udp.sendto(b'PONG_SHIRO', (opponent,oppPort))
                            continue
                        elif packetSet == b'RESET_COUNT_SHIRO':
                            # If peer reset their tunnel, we need to reset our sequence counter.
                            print("Packet sequence reset")
                            currentSequence = 0
                            continue
                        elif packetSet == b'PONG_SHIRO':
                            if first_run:
                                print("Connection established. Begin link play\r\n")
                                udp.sendto(b'RESET_COUNT_SHIRO', (opponent,oppPort)) 
                                # we know there's a peer because it responded to our ping
                                # tell it to reset its sequence counter
                                first_run = False
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
                            # logger.info(binascii.hexlify(payload))
                            ser.write(toSend)
                            if packetNum == 0: # if the first packet was the processed packet,  no need to go through the rest
                                break

                    except IndexError:
                        continue
                except ConnectionResetError:
                    continue
                    
        logger.info("listener stopped")        
                
    def sender(side,opponent):
        global ser
        global ping
        global state
        if side == "waiting":
            oppPort = 21002
        if side == "calling":
            oppPort = 21001
        sequence = 0
        packets = []
        first_run = True
        
        while(state != "netlink_disconnected"):
            if time.time() - ping >= 5:
                try:
                    udp.sendto(b'PING_SHIRO', (opponent,oppPort))
                except ConnectionResetError:
                    pass
                ping = time.time()
            raw_input = b''
            if ser.in_waiting > 0:
                raw_input += ser.read(ser.in_waiting)
            if len(raw_input) > 0 and printout:
                print(raw_input)
            try:
                payload = raw_input
                seq = str(sequence)
                if len(payload) > 0:
                    
                    packets.insert(0,(payload+dataSplit+seq.encode()))
                    if(len(packets) > 5):
                        packets.pop()
                        
                    for i in range(1): #send the data twice. May help with drops or latency    
                        ready = select.select([],[udp],[]) #blocking select  
                        if ready[1]:
                            udp.sendto(packetSplit.join(packets), (opponent,oppPort))
                                
                    sequence+=1
            except Exception as e: 
                print(e)
                
                continue
        try:
            udp.close()
            logger.info("sender stopped")
        except Exception as e:
            print(e)
             
    if state == "connecting":
        t1 = threading.Thread(target=listener)
        t2 = threading.Thread(target=sender,args=(side,opponent))
        if side == "waiting": #we're going to bind to a port. Some users may want to run two instances on one machine, so use different ports for waiting, calling
            Port = 21001
        if side == "calling":
            Port = 21002
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, 184)
        udp.setblocking(0)
        udp.bind(('', Port))

        t1.start()
        t2.start()
        while t1.is_alive:
            t1.join(2)
        while t2.is_alive:
            t2.join(2)

if __name__ == '__main__':
    try:
        com_port, speed, ms, dial_string, modem, ser = setup()
        state, opponent = initConnection(ms,dial_string)
        print(state,opponent)
        serial_exchange(ms,state,opponent)
    except KeyboardInterrupt:
        state = "netlink_disconnected"
        print('Interrupted')
        time.sleep(4)
        try:
            sys.exit(130)
        except SystemExit:
            os._exit(130)