Prerequisites:
Python 2.7 and pyserial module

Port forwards:
65432 TCP
20001 UDP
20002 UDP

Assuming a windows machine and Python run the tunnel like:
python tunnel_v2.py COM4 127.0.0.1

Replace COM4 with the com port of the USB modem and 127.0.0.1 with your opponent's IP address

For xband games, you need two player ids,  sp0 and mp7. sp0 for slave, or wait side. mp7 for master or dial side. In Netlink games you either select wait, or dial 7.