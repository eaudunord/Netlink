Prerequisites:
Python 2.7 and pyserial module

Port forwards:
65432 TCP
20001 UDP
20002 UDP

Assuming a windows machine and Python run the tunnel like:
python tunnel_v2.py COM4 127.0.0.1

Replace COM4 with the com port of the USB modem and 127.0.0.1 with your opponent's IP address