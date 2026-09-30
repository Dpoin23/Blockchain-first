"""Peer URLs are checked before a connection is opened."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from chain.errors import ChainError
from chain.peers import fetch_chain, normalize_origin


def test_loopback_and_private_origins_are_allowed():
    assert normalize_origin("http://127.0.0.1:5001/") == "http://127.0.0.1:5001"
    assert normalize_origin("http://10.0.0.8:5001") == "http://10.0.0.8:5001"
    assert normalize_origin("http://[::1]:5001") == "http://[::1]:5001"
    assert normalize_origin("http://localhost:5001") == "http://localhost:5001"


def test_hyphen_runs_are_rejected_without_backtracking():
    started = time.monotonic()
    with pytest.raises(ChainError):
        normalize_origin("http://" + ("-" * 180) + ":80")
    assert time.monotonic() - started < 0.5


def test_metadata_and_non_http_targets_are_rejected():
    rejected = [
        "http://169.254.169.254:80",
        "http://169.254.1.1:80",
        "http://[fe80::1]:5001",
        "http://224.0.0.1:5001",
        "http://0.0.0.0:5001",
        "file:///etc/passwd",
        "http://user:secret@127.0.0.1:5001",
        "http://127.0.0.1:5001/chain",
        "http://127.0.0.1",
        "http://2130706433:80",
        "gopher://127.0.0.1:70",
    ]
    for url in rejected:
        with pytest.raises(ChainError):
            normalize_origin(url)


def _serve(handler: type[BaseHTTPRequestHandler]) -> tuple[HTTPServer, threading.Thread]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_fetch_reads_json_and_ignores_redirects():
    class OkHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"chain": [{"index": 0}], "length": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254:80/")
            self.end_headers()

        def log_message(self, fmt, *args):
            return

    ok_server, _ok_thread = _serve(OkHandler)
    redirect_server, _redirect_thread = _serve(RedirectHandler)
    try:
        ok_port = ok_server.server_address[1]
        assert fetch_chain(f"http://127.0.0.1:{ok_port}") == [{"index": 0}]
        redirect_port = redirect_server.server_address[1]
        started = time.monotonic()
        assert fetch_chain(f"http://127.0.0.1:{redirect_port}") is None
        assert time.monotonic() - started < 1.5
    finally:
        ok_server.shutdown()
        redirect_server.shutdown()
        ok_server.server_close()
        redirect_server.server_close()


def test_closed_port_returns_none():
    assert fetch_chain("http://127.0.0.1:9") is None
