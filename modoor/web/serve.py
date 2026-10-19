"""Listen on 8765. With certs, TLS serves the app and plain HTTP redirects to HTTPS."""

from __future__ import annotations

import os
import selectors
import socket
import ssl
import threading
from pathlib import Path

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 8765
_HEADER_LIMIT = 8192
_CERT_DIR = Path(os.environ.get("MODOOR_CERT_DIR", "/certs"))


def cert_pair(directory: Path | None = None) -> tuple[Path, Path] | None:
    root = directory or _CERT_DIR
    cert = root / "fullchain.pem"
    key = root / "privkey.pem"
    if cert.is_file() and key.is_file():
        return cert, key
    return None


def https_location(path: str, host_header: str, public_url: str) -> str:
    """Public HTTPS URL for an HTTP request that arrived on the shared port."""
    target = path if path.startswith("/") else "/"
    base = (public_url or "").strip().rstrip("/")
    if not base.startswith("https://"):
        name = (host_header or "localhost").split(":")[0] or "localhost"
        base = "https://" + name
    return base + target


def _request_path_and_host(head: bytes) -> tuple[str, str]:
    lines = head.split(b"\r\n")
    parts = lines[0].decode("latin1", "replace").split(" ")
    path = parts[1] if len(parts) > 1 else "/"
    host = ""
    for line in lines[1:]:
        if line.lower().startswith(b"host:"):
            host = line.split(b":", 1)[1].strip().decode("latin1", "replace")
            break
    return path, host


def _read_headers(conn: socket.socket) -> bytes:
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < _HEADER_LIMIT:
        chunk = conn.recv(_HEADER_LIMIT - len(buf))
        if not chunk:
            break
        buf += chunk
    return buf


def _redirect(conn: socket.socket, public_url: str) -> None:
    head = _read_headers(conn)
    path, host = _request_path_and_host(head)
    loc = https_location(path, host, public_url).encode()
    conn.sendall(
        b"HTTP/1.1 301 Moved Permanently\r\n"
        b"Location: " + loc + b"\r\n"
        b"Content-Length: 0\r\n"
        b"Connection: close\r\n\r\n"
    )


def _inject_proto(data: bytes) -> bytes:
    sep = data.find(b"\r\n\r\n")
    if sep < 0:
        return data
    head = data[:sep]
    if b"\r\nx-forwarded-proto:" in b"\r\n" + head.lower():
        return data
    return head + b"\r\nX-Forwarded-Proto: https" + data[sep:]


def _splice(left: socket.socket, right: socket.socket) -> None:
    sel = selectors.DefaultSelector()
    sel.register(left, selectors.EVENT_READ)
    sel.register(right, selectors.EVENT_READ)
    try:
        while True:
            events = sel.select(timeout=300)
            if not events:
                break
            for key, _ in events:
                try:
                    chunk = key.fileobj.recv(65536)  # type: ignore[union-attr]
                except OSError:
                    return
                if not chunk:
                    return
                other = right if key.fileobj is left else left
                other.sendall(chunk)
    finally:
        sel.close()


def _proxy_tls(conn: socket.socket, upstream: tuple[str, int]) -> None:
    head = b""
    while b"\r\n\r\n" not in head and len(head) < _HEADER_LIMIT:
        chunk = conn.recv(_HEADER_LIMIT - len(head))
        if not chunk:
            return
        head += chunk
    remote = socket.create_connection(upstream, timeout=10)
    try:
        remote.sendall(_inject_proto(head))
        _splice(conn, remote)
    finally:
        remote.close()


def handle_client(
    conn: socket.socket,
    *,
    ssl_ctx: ssl.SSLContext | None,
    upstream: tuple[str, int],
    public_url: str,
) -> None:
    try:
        conn.settimeout(30)
        peeked = conn.recv(1, socket.MSG_PEEK)
        if ssl_ctx is not None and peeked[:1] == b"\x16":
            tls = ssl_ctx.wrap_socket(conn, server_side=True)
            try:
                _proxy_tls(tls, upstream)
            finally:
                tls.close()
            return
        _redirect(conn, public_url)
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _wait_until_open(host: str, port: int, timeout: float = 30) -> None:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"app did not listen on {host}:{port}")


def _serve_tls(cert: Path, key: Path, public_url: str) -> None:
    import signal

    import uvicorn

    from modoor.web.app import app

    upstream_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    upstream_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    upstream_sock.bind(("127.0.0.1", 0))
    upstream_sock.listen(128)
    upstream_sock.set_inheritable(True)
    upstream_port = upstream_sock.getsockname()[1]

    def _app() -> None:
        config = uvicorn.Config(
            app,
            fd=upstream_sock.fileno(),
            proxy_headers=True,
            forwarded_allow_ips="*",
            log_level="info",
        )
        uvicorn.Server(config).run()

    threading.Thread(target=_app, name="modoor-http", daemon=True).start()
    _wait_until_open("127.0.0.1", upstream_port)

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(cert, key)
    upstream = ("127.0.0.1", upstream_port)

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((LISTEN_HOST, LISTEN_PORT))
    server.listen(128)
    print(
        f">> TLS on :{LISTEN_PORT}; plain HTTP redirects to HTTPS",
        flush=True,
    )

    def _accept() -> None:
        while True:
            try:
                conn, _addr = server.accept()
            except OSError:
                return
            threading.Thread(
                target=handle_client,
                args=(conn,),
                kwargs={
                    "ssl_ctx": ctx,
                    "upstream": upstream,
                    "public_url": public_url,
                },
                daemon=True,
            ).start()

    threading.Thread(target=_accept, name="modoor-tls", daemon=True).start()

    def _stop(*_args: object) -> None:
        server.close()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while True:
        signal.pause()


def serve() -> None:
    public_url = os.environ.get("MODOOR_WEBUI_URL", "")
    found = cert_pair()
    if found is None:
        import uvicorn

        from modoor.web.app import app

        print(f">> no certs, HTTP on :{LISTEN_PORT}", flush=True)
        uvicorn.run(
            app,
            host=LISTEN_HOST,
            port=LISTEN_PORT,
            proxy_headers=True,
            forwarded_allow_ips="*",
        )
        return
    cert, key = found
    _serve_tls(cert, key, public_url)


def main() -> None:
    serve()


if __name__ == "__main__":
    main()
