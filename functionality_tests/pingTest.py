import select
import socket
import sys
import time
pinging = True
Port = 20001
oppPort = 20002
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp.setblocking(0)
udp.bind(('', Port))
pingCount = 0
lastPing = 0
ping = time.time()
pong = time.time()
jitterStore = []
pingStore = []
maxPing = 0
maxJitter = 0
sent = 0

opponent = input('Enter IP address to connect to >> ')
start = None
while True:
    start = input('Enter 1 to wait or 2 to initiate ping >> ')
    if start in ('1','2'):
        break
if start == '1':
    pinged = False
else:
    pinged = True

while True:
    try:
        if pinged == True:
            udp.sendto(b'PING_SHIRO', (opponent,oppPort))
        ping = time.time()
        while (time.time() - ping) < 0.3:
            ready = select.select([udp],[],[],0)
            if ready[0]:
                packetSet = udp.recv(1024)
                if packetSet == b'PING_SHIRO':
                    udp.sendto(b'PONG_SHIRO', (opponent,oppPort))
                    pinged = True
                if packetSet == b'PONG_SHIRO':
                    pong = time.time()
                    pingResult = round((pong-ping)*1000,2)
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
                    sys.stdout.write('Ping: %s Max: %s | Jitter: %s Max: %s | Avg Ping: %s |  Avg Jitter: %s          \r' % (pingResult,maxPing,jitter, maxJitter,pingAvg,jitterAvg))
                    lastPing = pingResult
    except KeyboardInterrupt:
        break