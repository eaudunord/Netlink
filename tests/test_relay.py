import logging
import os
import socket
import sys
import threading
import time

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tunnel'))

import netlink


class FakeSerial(object):
    def __init__(self):
        self.timeout = 0
        self.rx = bytearray()
        self.lock = threading.Lock()

    def feed(self, data):
        with self.lock:
            self.rx.extend(data)

    @property
    def in_waiting(self):
        with self.lock:
            return len(self.rx)

    def read(self, size=1):
        deadline = time.time() + (self.timeout or 0)
        while True:
            with self.lock:
                if self.rx:
                    out = bytes(self.rx[:size])
                    del self.rx[:size]
                    return out
            if time.time() >= deadline:
                return b''
            time.sleep(0.005)

    def write(self, data):
        return len(data)


class AuthServer(object):
    def __init__(self):
        self.received = bytearray()
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen(1)
        self.port = self.listener.getsockname()[1]
        thread = threading.Thread(target=self.run)
        thread.daemon = True
        thread.start()

    def run(self):
        conn, _ = self.listener.accept()
        conn.settimeout(0.2)
        conn.recv(64)
        conn.sendall(b'\x01')
        self.ready.set()
        while not self.stop.is_set():
            try:
                data = conn.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            self.received.extend(data)
        conn.close()

    def close(self):
        self.stop.set()
        self.listener.close()


def test_client_bytes_reach_the_server():
    server = AuthServer()
    ser = FakeSerial()

    nl = netlink.Netlink.__new__(netlink.Netlink)
    nl.logger = logging.getLogger('netlink-test')

    cfg = {
        'host': '127.0.0.1',
        'port': str(server.port),
        'shared_secret': 'hunter2',
        'ppp_fix_delimiters': 'true',
    }

    relay = threading.Thread(
        target=nl.netlink_standard_server, args=(cfg,), kwargs={'ser': ser})
    relay.daemon = True
    relay.start()

    assert server.ready.wait(5), "relay never authenticated"
    ser.feed(b'\x7ehello\x7e')

    deadline = time.time() + 5
    while time.time() < deadline and b'hello' not in bytes(server.received):
        time.sleep(0.05)

    server.close()
    relay.join(timeout=5)

    assert b'hello' in bytes(server.received)
