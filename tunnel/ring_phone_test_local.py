from xband_config import my_ip
from xband_config import opponent_ip
from xband_config import cpu_id_spoof
from xband_config import opponent_port
from xband_config import opponent_id
from xband_config import local_port
from datetime import datetime
import select
import socket
import sip_ring

# opponent = opponent_ip
# sip = sip_ring.SIP('user','',my_ip,opponent_port,local_ip = my_ip,local_port=local_port)
# sip.call(opponent_id,3)

def ringPhone():
    opponent = opponent_ip
    PORT = 65433
    sock_send = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_send.settimeout(15)
    print(datetime.now(), "Calling opponent")

    try:
        sock_send.connect((opponent, PORT))
        sock_send.sendall(b"RESET")
        ready = select.select([sock_send], [], [])
        if ready[0]:
            data = sock_send.recv(1024)
            if data == b'ACK RESET':
                sip = sip_ring.SIP('user','',opponent,opponent_port,local_ip = my_ip,local_port=local_port)
                sip.call(opponent_id,3)
                sock_send.sendall(b'RING')
                data = sock_send.recv(1024)
                if data == b'ANSWERING':
                    print(datetime.now(), "Answering")
                    return opponent

    except socket.error:
        return "error"

ringPhone()