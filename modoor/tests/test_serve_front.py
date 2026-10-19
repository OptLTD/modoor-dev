from __future__ import annotations

import socket
import ssl
import subprocess
import threading
from pathlib import Path

from modoor.web.serve import cert_pair, handle_client, https_location


def test_https_location_prefers_public_https_url():
    assert (
        https_location("/login?next=/home", "evil.example:80", "https://fleet.example")
        == "https://fleet.example/login?next=/home"
    )


def test_https_location_uses_request_host_when_url_is_not_https():
    assert https_location("/a", "app.example:80", "http://127.0.0.1:8765") == "https://app.example/a"


def test_cert_pair_requires_both_files(tmp_path: Path):
    assert cert_pair(tmp_path) is None
    (tmp_path / "fullchain.pem").write_text("cert", encoding="utf-8")
    assert cert_pair(tmp_path) is None
    (tmp_path / "privkey.pem").write_text("key", encoding="utf-8")
    cert, key = cert_pair(tmp_path)
    assert cert.name == "fullchain.pem"
    assert key.name == "privkey.pem"


def _listen() -> tuple[socket.socket, int]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(8)
    return sock, sock.getsockname()[1]


def test_plain_http_redirects_and_tls_is_proxied(tmp_path: Path):
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(tmp_path / "privkey.pem"),
            "-out",
            str(tmp_path / "fullchain.pem"),
            "-days",
            "1",
            "-nodes",
            "-subj",
            "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )
    cert, key = cert_pair(tmp_path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)

    upstream, upstream_port = _listen()
    front, front_port = _listen()
    seen: dict[str, bytes] = {}

    def _upstream() -> None:
        conn, _addr = upstream.accept()
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data += chunk
        seen["req"] = data
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
        conn.close()

    def _front() -> None:
        while True:
            try:
                conn, _addr = front.accept()
            except OSError:
                return
            handle_client(
                conn,
                ssl_ctx=ctx,
                upstream=("127.0.0.1", upstream_port),
                public_url="https://fleet.example",
            )

    threading.Thread(target=_upstream, daemon=True).start()
    threading.Thread(target=_front, daemon=True).start()

    plain = socket.create_connection(("127.0.0.1", front_port), timeout=3)
    plain.sendall(b"GET /login HTTP/1.1\r\nHost: app.example\r\n\r\n")
    redirected = plain.recv(1024)
    plain.close()
    assert b"301" in redirected
    assert b"Location: https://fleet.example/login" in redirected

    client = ssl.create_default_context()
    client.check_hostname = False
    client.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection(("127.0.0.1", front_port), timeout=3)
    tls = client.wrap_socket(raw, server_hostname="localhost")
    tls.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
    body = b""
    while b"OK" not in body:
        chunk = tls.recv(1024)
        if not chunk:
            break
        body += chunk
    tls.close()
    assert body.endswith(b"OK")
    assert b"X-Forwarded-Proto: https" in seen["req"]
    assert b"GET /health" in seen["req"]

    front.close()
    upstream.close()
