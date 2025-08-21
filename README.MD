An internet tunneler for connecting Netlink and Xband games

The tunneler is included in the latest Dreamcast Live Dreampi releases. I do not directly maintain those releases so cannot guarantee functionality.

<<<<<<< HEAD
Now included is link_cable.py which can be used to tunnel Dreamcast link cable games online using a Dreamcast "Coder's cable." This is still in early development and feedback is appreciated.

=======
>>>>>>> latest
modemClass.py is borrowed/lifted and slightly modified from the Dreampi script. Thanks to Kazade et al for creating that invaluable tool.

[Original Dreampi Script](https://github.com/Kazade/dreampi)

You should be able to use this for other generic modem to modem communications over the net. You will need to modify how the modem waiting for a call initializes. If you can modify the init string, appending "dt0" should cause that modem to dial out and wait for a "RING". See the README in the releases for how to call the waiting modem.
