import socket
import threading

import pytest
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

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
                assert w.accepted_subprotocol == "binary"
                w.send_bytes(b"\x01\x02binary")
                assert w.receive_bytes() == b"\x01\x02binary"
    finally:
        server.close()


def test_proxy_closes_when_no_vnc(monkeypatch):
    monkeypatch.setattr(state, "VNC_PORT", 59999)  # 닫힌 포트
    with TestClient(_tiny_app()) as c:
        with c.websocket_connect("/ws", subprotocols=["binary"]) as w:
            assert w.accepted_subprotocol == "binary"
            # 프록시가 accept 후 VNC 연결 실패 → ws.close(1000). 서버가 닫았으므로
            # 이후 receive는 WebSocketDisconnect(1000)를 던진다 (브로드 Exception 아님).
            with pytest.raises(WebSocketDisconnect) as exc:
                w.receive_bytes()
            assert exc.value.code == 1000
