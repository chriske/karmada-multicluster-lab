#!/usr/bin/env python3
"""Forward the initializer's loopback NodePort to kind's host mapping."""
import selectors
import socket
import socketserver


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        try:
            upstream = socket.create_connection(('127.0.0.1', 16447), timeout=10)
        except OSError:
            return
        with upstream, selectors.DefaultSelector() as selector:
            upstream.settimeout(None)
            selector.register(self.request, selectors.EVENT_READ, upstream)
            selector.register(upstream, selectors.EVENT_READ, self.request)
            while True:
                for key, _ in selector.select():
                    try:
                        data = key.fileobj.recv(65536)
                        if not data:
                            return
                        key.data.sendall(data)
                    except OSError:
                        return


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


with Server(('127.0.0.1', 32443), Relay) as server:
    server.serve_forever()
