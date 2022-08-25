An internet tunneler for connecting Netlink and Xband games

v4.2-beta is the latest tested as working online

This can be integrated into Dreampi to add Netlink support. See the releases for the required updated scripts or visit Sega Saturn Shiro! Discord for additional help.

modemClass.py is borrowed and slightly modified from the Dreampi script. Thanks to Kazade et al for creating that invaluable tool.

[Original Dreampi Script](https://github.com/Kazade/dreampi)

You should be able to use this for other generic modem to modem communications over the net. You will need to modify how the modem waiting for a call initializes. If you can modify the init string, appending "dt0" should cause that modem to dial out and wait for a "RING". See the README in the releases for how to call the waiting modem.
