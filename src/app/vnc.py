"""Starlette WebSocket ↔ TCP(VNC) 브리지. manager.relay_websockify의 Starlette판."""

import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from app import state


async def proxy(ws: WebSocket) -> None:
    # RFC 6455: 클라이언트가 요청하지 않은 Sec-WebSocket-Protocol을 응답하면
    # 브라우저가 핸드셰이크를 거부한다(1006). noVNC 1.6은 서브프로토콜을 요청하지
    # 않으므로, 요청이 있을 때만 첫 번째 값을 그대로 되돌려준다.
    offered = ws.headers.get("sec-websocket-protocol", "")
    await ws.accept(subprotocol=offered.split(",")[0].strip() or None)
    try:
        reader, writer = await asyncio.open_connection(state.VNC_HOST, state.VNC_PORT)
    except OSError:
        await ws.close()
        return

    async def c2s():
        try:
            while True:
                writer.write(await ws.receive_bytes())
                await writer.drain()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            writer.close()

    async def s2c():
        try:
            while True:
                data = await reader.read(32768)
                if not data:
                    break
                await ws.send_bytes(data)
        except (WebSocketDisconnect, RuntimeError):
            pass

    t1 = asyncio.create_task(c2s())
    t2 = asyncio.create_task(s2c())
    _, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
