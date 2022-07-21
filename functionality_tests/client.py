from re import ASCII
import socket
import select
import time

PORT = 65433
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
# tcp.bind(('', PORT))
# tcp.listen(5)

tcp.connect(("127.0.0.1", 65434))
for i in range(10):
    payload = bytes(str(i),"ASCII")
    tcp.sendall(payload)
tcp.sendall(b'stop')
tcp.shutdown(socket.SHUT_RDWR)
tcp.close()


time.sleep(5)
print("second connect")
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.connect(("www.google.com", 80))
tcp.shutdown(socket.SHUT_RDWR)
tcp.close()

print("re-connecting")
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.connect(("127.0.0.1", 65434))
for i in range(10):
    payload = bytes(str(i),"ASCII")
    tcp.sendall(payload)
tcp.sendall(b'stop')
tcp.shutdown(socket.SHUT_RDWR)
tcp.close()
print("client done")
