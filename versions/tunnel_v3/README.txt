tunnel_v3_2.py is the latest version tested as working

Prerequisites:
Python 2.7 and pyserial module

Port forwards:
65432 TCP
20001 UDP
20002 UDP

Assuming a windows machine and Python run the tunnel like:
python tunnel_v3_2.py COM4

Replace COM4 with the com port of the USB modem and optionally add printout to the command to enable console printing.

For xband games, you need two player ids,  sp0 and mp#ipaddress#. sp for slave, or wait side. mp#ipaddress# for master or dial side where IP address is zero padded and no decimals e.g. 127000000001 for 127.0.0.1. In Netlink games you either select wait, or dial #ipaddress# in the same format just described.