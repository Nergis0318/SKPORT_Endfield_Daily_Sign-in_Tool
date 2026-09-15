import socket
import threading

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from app import state
from app.vnc import proxy


def _echo(conn: socket.socket):
    with conn:
        while data := conn.recv(32768):
            conn.sendall(data)


def _tiny_app():
    t = FastAPI()

    @t.websocket("/ws")
    async def ep(ws: WebSocket):
        await proxy(ws)

    return t


def test_proxy_echoes_binary(monkeypatch):
    server = socket.create_server(("127.0.0.1", 0))
    monkeypatch.setattr(state, "VNC_PORT", server.getsockname()[1])
    threading.Thread(target=lambda: _echo(server.accept()[0]), daemon=True).start()
    try:
        with TestClient(_tiny_app()) as c:
            with c.websocket_connect("/ws", subprotocols=["binary"]) as w:
                w.send_bytes(b"\x01\x02binary")
                assert w.receive_bytes() == b"\x01\x02binary"
    finally:
        server.close()


def test_proxy_closes_when_no_vnc(monkeypatch):
    monkeypatch.setattr(state, "VNC_PORT", 59999)  # 닫힌 포트
    with TestClient(_tiny_app()) as c:
        with c.websocket_connect("/ws", subprotocols=["binary"]) as w:
            import pytest

            with pytest.raises(Exception):
                w.send_bytes(b"ping")
                w.receive_bytes()