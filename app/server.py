"""Tiny HTTP demo app: no non-standard Python dependencies."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import socket
import threading
import time
from urllib.parse import urlparse, parse_qs

request_count = 0
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        global request_count
        if self.path == '/healthz':
            self._send(200, b'ok\n', 'text/plain; charset=utf-8')
        elif self.path.startswith('/burn'):
            # CPU-bound endpoint for HPA resource metrics; bounded by ?ms=
            ms = min(500, max(10, int(parse_qs(urlparse(self.path).query).get('ms', ['100'])[0])))
            deadline = time.perf_counter() + ms / 1000.0
            x = 0
            while time.perf_counter() < deadline:
                x = (x * 1664525 + 1013904223) & 0xFFFFFFFF
            with lock:
                request_count += 1
            self._send(200, b'burn ok\n', 'text/plain')
        elif self.path == '/metrics':
            with lock:
                count = request_count
            payload = f'# HELP lab_http_requests_total Requests to the demo application\n# TYPE lab_http_requests_total counter\nlab_http_requests_total {count}\n'
            self._send(200, payload.encode(), 'text/plain; version=0.0.4')
        elif self.path == '/':
            with lock:
                request_count += 1
            self._send(200, json.dumps({
                'pod': os.getenv('POD_NAME', socket.gethostname()),
                'node': os.getenv('NODE_NAME', 'unknown'),
                'note': 'Cluster identity is added by per-member telemetry labels, not inferred from the Pod.'
            }).encode() + b'\n', 'application/json')
        else:
            self._send(404, b'not found\n', 'text/plain')

    def _send(self, code, body, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
