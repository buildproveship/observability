"""Owned synthetic TDM listener responses. No TDM runtime, keys or private data.

Test classification: e2e
Review status: Not Reviewed
Evidence: synthetic
Scope: test fixture server mounted alone into the fixture container (standard
library only, no package imports); it answers the probe with one synthetic case.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import time

CASES = ('available', 'denied', 'redirect', 'malformed', 'extra-field', 'timeout', 'oversized')


def handler_for(case: str) -> type[BaseHTTPRequestHandler]:
    if case not in CASES:
        raise ValueError('Unknown synthetic case')

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            status, body = 200, b'{"status":"available"}'
            if self.path == '/health-ok':
                # Redirect trap: would incorrectly succeed if redirects were followed.
                pass
            elif self.path != '/health':
                status, body = 404, b'{}'
            elif case == 'denied':
                status, body = 403, b'{"error":"Test data unavailable"}'
            elif case == 'redirect':
                status, body = 302, b'{}'
            elif case == 'malformed':
                body = b'not-json'
            elif case == 'extra-field':
                body = b'{"status":"available","synthetic_extra":true}'
            elif case == 'timeout':
                time.sleep(3)
            elif case == 'oversized':
                body = b'{"status":"available"}' + b' ' * 2048
            self.send_response(status)
            if status == 302:
                self.send_header('Location', '/health-ok')
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected bounded probe cancellation for timeout fixture.

        def log_message(self, format: str, *args: object) -> None:
            # Never record request headers, bodies or diagnostics.
            print('synthetic request handled', flush=True)

    return Handler


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 3102), handler_for(os.environ.get('FIXTURE_CASE', 'available'))).serve_forever()
