import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


@dataclass
class ReceivedRequest:
    path: str
    headers: dict[str, str]
    body: bytes


@dataclass
class FakeReceiver:
    """A local HTTP server standing in for a customer's webhook receiver."""

    url: str
    status_code: int = 200
    delay_seconds: float = 0
    extra_headers: dict[str, str] = field(default_factory=dict)
    requests: list[ReceivedRequest] = field(default_factory=list)


def _make_handler(receiver: FakeReceiver) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self._record()

        def do_GET(self):
            self._record()

        def _record(self):
            length = int(self.headers.get('Content-Length', 0))
            receiver.requests.append(
                ReceivedRequest(path=self.path, headers=dict(self.headers), body=self.rfile.read(length))
            )
            time.sleep(receiver.delay_seconds)
            self.send_response(receiver.status_code)
            for name, value in receiver.extra_headers.items():
                self.send_header(name, value)
            self.send_header('Content-Length', '0')
            self.end_headers()

        def log_message(self, format, *args):
            pass

    return Handler


@pytest.fixture
def fake_receiver():
    receiver = FakeReceiver(url='')
    server = ThreadingHTTPServer(('127.0.0.1', 0), _make_handler(receiver))
    server.daemon_threads = True
    receiver.url = f'http://127.0.0.1:{server.server_port}/hook'
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield receiver
    server.shutdown()
    server.server_close()
