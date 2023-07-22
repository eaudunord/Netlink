import socket
import time
import select
import threading
import sys
from random import randint
from multiprocessing import Queue, Process

latency = 0.0
jitter = False
jitterSpike = False

numThreads = 16
threads = []
arguments = {}

for i in range(1,len(sys.argv)):
    argument = sys.argv[i].split('=')
    arguments[argument[0]] = argument[1]

player1 = arguments['player1']
player2 = arguments['player2']
if 'latency' in arguments:
    latency = float(arguments['latency'])

print(player1,player2,latency)





def tcp_forwarder(conn,connected): #single thread
    tcp_fwd = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        #data = conn.recv(1024)
        if connected == player1:
            tcp_fwd.connect((player2,65432))
        elif connected == player2:
            tcp_fwd.connect((player1,65432))
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

def udp_sender(q2): #single thread
    print("UDP Sender Started")
    # last1 = time.time()
    # last2 = time.time()
    # f = open('logs/20001Log.bin','wb')
    while True:
        if not q2.empty():
            r = q2.get()
            if r is None:
                # f.close()
                return
            data, opponent, port = r
            udp3.sendto(data,(opponent,port))
            # if port == 20001:
            #     delta1 = round((time.time() - last1),3)
            #     last1 = time.time()
                #print(f'\rport 2001 delta: {delta1}',end='',flush=True)
                # f.write(str(delta1).encode()+b'\t'+data.split(b'<dataSplit>')[0]+b'\r\n')
            # if port == 20002:
            #     delta2 = time.time() - last2
            #     last2 = time.time()
            #     print(f'port 2002 delta: {delta2}')
            

def udp_forwarder(q,q2): #run multiple threads of this function
    while True:
        if not q.empty():
            r = q.get()
            time.sleep(latency)
            if jitter:
                time.sleep(randint(0,15)*.001)
            if jitterSpike:
                num = randint(0,10)
                if num == 7:
                    time.sleep(0.02)
            if r is None:
                time.sleep(2)
                q2.put(r)
                return
            q2.put(r)
        


def udp_listener(q): #single thread
    timeout = 45
    ts = time.time()
    while True:
        if time.time() - ts > timeout:
            for i in range(numThreads-1):
                q.put(None)
            time.sleep(2)
            q.put(None)
            return
        ready1 = select.select([udp1], [], [],0)
        ready2 = select.select([udp2], [], [],0)
        if ready1[0]:
            data, addr = udp1.recvfrom(1024)
            if addr[0] == player1:
                opponent = player2
            else:
                opponent = player1
            q.put([data,opponent,20001])
            ts = time.time()
        if ready2[0]:
            data, addr = udp2.recvfrom(1024)
            if addr[0] == player1:
                opponent = player2
            else:
                opponent = player1
            q.put([data,opponent,20002])
            ts = time.time()

def startup():
    print("listening")
    while True:
        ready = select.select([tcp], [], [],0)
        if ready[0]:
            conn, addr = tcp.accept()
            connected = addr[0]
            return [conn,connected]

if __name__ == '__main__':
    PORT = 65432
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.settimeout(120)
    tcp.bind(('', PORT))
    tcp.setblocking(0)
    tcp.listen(5)

    udp1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp1.setblocking(0)
    udp1.bind(('', 20001))
    udp2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp2.setblocking(0)
    udp2.bind(('', 20002))
    udp3 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


    

    def process():
        q = Queue()
        q2 = Queue()

        conn, connected = startup()
        print('connection from %s' % connected)
        tcp_forwarder(conn,connected)
        t1 = threading.Thread(target=udp_listener, args=(q,))
        t2 = threading.Thread(target=udp_sender, args=(q2,))

        # t1 = Process(target=udp_listener, args=(q,))
        # t2 = Process(target=udp_sender, args=(q2,))
        
        t1.start()
        t2.start()
        for i in range(numThreads):
            # thread = threading.Thread(target = udp_forwarder, args=(q,q2))
            thread = Process(target = udp_forwarder, args=(q,q2))
            thread.start()
            threads.append(thread)
        t1.join()
        for thread in threads:
            thread.join()
        t2.join()

    while True:
        try:
            process()
        except KeyboardInterrupt:
            sys.exit()

# #based on this working test
# import threading
# import time
# from multiprocessing import Queue
# import sys


# numThreads = 4
# def writer(q):
#     for i in range(30):
#         time.sleep(1)
#         message = f'I am message {i}'
#         q.put(message)
#     for i in range(numThreads-1):
#         q.put(None)
#     time.sleep(2)
#     q.put(None)

# def reader(q,q2):
#     while True:
#         if not q.empty():
#             item = q.get()
#             if item == None:
#                 time.sleep(2)
#                 q2.put(item)
#                 return
#             time.sleep(1)
#             q2.put(item)
            

# def sender(q2):
#     while True:
#         if not q2.empty():
#             item = q2.get()
#             if item == None:
#                 return
#             print(item)

# def process():
#     q = Queue()
#     q2 = Queue()
#     t1 = threading.Thread(target=writer, args=(q,))
#     t1.start()
#     t2 = threading.Thread(target = sender, args=(q2,))
#     t2.start()

#     threads = []
#     for i in range(numThreads):
#         thread = threading.Thread(target = reader, args=(q,q2))
#         thread.start()
#         threads.append(thread)

#     t1.join()
#     for thread in threads:
#         thread.join()
#     t2.join()

# while True:
#     try:
#         process()
#     except KeyboardInterrupt:
#         sys.exit()


    