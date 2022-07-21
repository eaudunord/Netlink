import socket
import select

PORT = 65434
tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp.bind(('', PORT))
tcp.listen(5)

while True:
    ready = select.select([tcp], [], [],5)
    if ready[0]:
        conn, addr = tcp.accept()
        try:
            data = conn.recv(1024)
            if data == b'stop':
                break
            else:
                print(data)
        except:
            pass
        finally:
            conn.shutdown(socket.SHUT_RDWR)
            conn.close()
    if not ready[0]:
        break

while True:
    ready = select.select([tcp], [], [],5)
    if ready[0]:
        conn, addr = tcp.accept()
        try:
            data = conn.recv(1024)
            if data == b'stop':
                break
            else:
                print(data)
        except:
            pass
        finally:
            tcp.shutdown(socket.SHUT_RDWR)
            tcp.close()
    if not ready[0]:
        break
if conn:
    print("conn exists")
else:
    print("conn is dead")
print("listener stopped")
