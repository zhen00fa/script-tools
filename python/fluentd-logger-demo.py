#!/usr/bin/env python3

import tracemalloc
import socket
import logging
import logging.config
import time
import eventlet
import threading

eventlet.monkey_patch()
tracemalloc.start()

class MyThreadLocal:
    def __init__(self):
        self.__attrs = {}

    def __setattr__(self, name, value):
        if name.startswith("_MyThreadLocal"):
            super().__setattr__(name, value)
            return
        self.__attrs[name] = value


class MyTester:
    def __init__(self):
        self.socket = None
        self.lock = threading.Lock()
        self.last_error = threading.local()
        #self.last_error = MyThreadLocal()

    def log(self, message):
        with self.lock:
            if self.socket:
                return False
            self._log_internal(message)

    def _log_internal(self, message):

        try:
            self._send_data(message)
            return True
        except socket.error as e:
            self._close()
            return False

    def clear_last_error(self, _thread_id=None):
        if hasattr(self.last_error, 'exception'):
            delattr(self.last_error, 'exception')

    def _close(self):
        try:
            sock = self.socket
            if sock:
                try:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except socket.error:
                        pass
                finally:
                    try:
                        sock.close()
                    except socket.error:
                        pass
        finally:
            self.socket = None
            self.clear_last_error()

    def _send_data(self, message):
        self.connect_socket("localhost", 24224)

    @profile
    def connect_socket(self, host, port):
        sock = None
        if not self.socket:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.connect((host, port))
            except Exception as e:
                self.last_error.exception = e
                try:
                    sock.close()
                except:
                    pass
                raise
            else:
                self.socket = sock


pool = eventlet.GreenPool()
obj = MyTester()
for i in range(1000):
    pool.spawn(obj.log, b"localhost")

pool.waitall()
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
print("[ Top 10 ]")
for stat in top_stats[:10]:
    print(stat)
time.sleep(5)



# python3 -m memory_profiler xxx.py