"""Scalable serving: a pre-bound SO_REUSEPORT listener + prefork workers.

The pure-Python token ciphers are CPU-bound (GIL-limited), so throughput scales
with worker processes, not threads. serve_forked binds one listening socket with
SO_REUSEPORT and forks N workers that all accept on it; the OS load-balances
connections. Shared state (TID lists, result cache) is coordinated through the
database, so workers stay stateless.

NOTE: the serial backend owns a single physical port, so run it with workers=1
(or one worker per module on distinct ports). The virtual backend scales freely.
"""

from __future__ import annotations
import os
import socket
import ssl
import signal


def make_listener(host: str, port: int, backlog: int = 256) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    s.bind((host, port))
    s.listen(backlog)
    return s


def make_tls_context(certfile: str, keyfile: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(certfile=certfile, keyfile=keyfile)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def _serve_one(listener: socket.socket, build_adapter, idl_path: str,
               tls_ctx: ssl.SSLContext | None):
    """Accept loop for a single worker, using thriftpy2 processor per connection."""
    import thriftpy2
    from thriftpy2.thrift import TProcessor
    from thriftpy2.protocol import TBinaryProtocolFactory
    from thriftpy2.transport import TBufferedTransportFactory, TSocket

    mod = thriftpy2.load(idl_path, module_name="prismtoken_thrift")
    processor = TProcessor(mod.TokenApi, build_adapter(mod))
    iproto = TBinaryProtocolFactory()
    itrans = TBufferedTransportFactory()

    while True:
        try:
            conn, _ = listener.accept()
        except (InterruptedError, OSError):
            continue
        if tls_ctx is not None:
            try:
                conn = tls_ctx.wrap_socket(conn, server_side=True)
            except ssl.SSLError:
                conn.close()
                continue
        client = TSocket()
        client.sock = conn
        trans = itrans.get_transport(client)
        proto = iproto.get_protocol(trans)
        try:
            while True:
                processor.process(proto, proto)
        except Exception:
            pass
        finally:
            trans.close()


def serve_forked(build_adapter, host: str, port: int, idl_path: str,
                 workers: int = 1, tls_certfile: str = "", tls_keyfile: str = ""):
    """build_adapter(mod) -> a thriftpy2 service handler bound to the loaded IDL."""
    listener = make_listener(host, port)
    tls_ctx = make_tls_context(tls_certfile, tls_keyfile) if tls_certfile else None

    children = []
    for _ in range(max(1, workers) - 1):
        pid = os.fork()
        if pid == 0:
            _serve_one(listener, build_adapter, idl_path, tls_ctx)
            os._exit(0)
        children.append(pid)

    def _reap(signum, frame):
        for pid in children:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _reap)
    signal.signal(signal.SIGINT, _reap)
    try:
        _serve_one(listener, build_adapter, idl_path, tls_ctx)   # parent also serves
    finally:
        _reap(None, None)
