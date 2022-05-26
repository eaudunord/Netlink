from socket import socket


import socket
HOST = "127.0.0.1"
PORT = 1337
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.connect(("127.0.0.1", PORT))
tcp.sendall(b"RING\r\n")
tcp.sendall(b'CONNECT\r\n')