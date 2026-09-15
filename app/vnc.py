"""Starlette WebSocket ↔ TCP(VNC) 브리지. manager.relay_websockify의 Starlette판."""
import asyncio

from fastapi import WebSocket, WebSocketDisconnect

from app import state


async def proxy(ws: WebSocket) -> None:
    await ws.accept(subprotocol="binary")
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