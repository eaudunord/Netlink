import socket
import time
import select
import threading
from random import randint


PORT = 65432
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.settimeout(120)
tcp.bind(('', PORT))
tcp.setblocking(0)
tcp.listen(5)
latency = 0
jitter = False


def tcp_forwarder(conn,connected):
    tcp_fwd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        #data = conn.recv(1024)
        if connected == "192.168.0.80":
            tcp_fwd.connect(("192.168.0.79",65432))
        elif connected == "192.168.0.79":
            tcp_fwd.connect(("192.168.0.80",65432))
    except:
        print("socket error")
        return
    while True:
        ready1 = select.select([conn], [], [],0)
        ready2 = select.select([tcp_fwd], [], [],0)
        if ready1[0]:
            data = conn.recv(1024)
            tcp_fwd.sendall(data)
        if ready2[0]:
            data = tcp_fwd.recv(1024)
            conn.sendall(data)
            if data == b'g2gip':
                return

def udp_forwarder():
    udp1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp1.setblocking(0)
    udp1.bind(('', 20001))
    udp2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp2.setblocking(0)
    udp2.bind(('', 20002))
    timeout = 90
    ts = time.time()
    while True:
        if time.time() - ts > timeout:
                return
        ready1 = select.select([udp1], [], [],0)
        ready2 = select.select([udp2], [], [],0)
        if ready1[0]:
            data, addr = udp1.recvfrom(1024)
            if addr[0] == "192.168.0.80":
                opponent = "192.168.0.79"
            else:
                opponent = "192.168.0.80"
            time.sleep(latency)
            if jitter:
                time.sleep((randint(0,10)*.001))
            udp1.sendto(data,(opponent,20002))
            ts = time.time()
        if ready2[0]:
            data, addr = udp2.recvfrom(1024)
            if addr[0] == "192.168.0.80":
                opponent = "192.168.0.79"
            else:
                opponent = "192.168.0.80"
            time.sleep(latency)
            if jitter:
                time.sleep((randint(0,10)*.001))
            udp2.sendto(data,(opponent,20001))
            ts = time.time()
    
while True:
    ready = select.select([tcp], [], [],0)
    if ready[0]:
        conn, addr = tcp.accept()
        connected = addr[0]
        print('connection from %s' % connected)
        t1 = threading.Thread(target=tcp_forwarder,args=(conn,connected))
        t1.start()
        t1.join()
        t2 = threading.Thread(target=udp_forwarder)
        t2.start()
        t2.join()