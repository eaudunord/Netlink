# echo-client.py

import socket

HOST = "97.116.177.33"  # The server's hostname or IP address
PORT = 65432  # The port used by the server

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect((HOST, PORT))
    s.sendall(b"Hello, world")
    data, addr = s.recv(1024)

print(f"Received {data!r} from {addr}")