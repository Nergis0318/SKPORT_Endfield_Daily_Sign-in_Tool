"""httpx 기반 텔레그램 알림. 무자격 스킵, 무예외."""
import asyncio
import os

import httpx

from app import state


async def send_telegram(bot_token: str, chat_id: str, text: str, client=None) -> bool:
    if not bot_token or not chat_id:
        return False
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=15)
    try:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[warn] telegram failed: {e}", flush=True)
        return False
    finally:
        if owned:
            await client.aclose()


async def notify(text: str) -> None:
    if state.state["settings"]["telegram"]:
        await send_telegram(os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", ""), text)


def notify_sync(text: str) -> None:
    """Executor 스레드용 동기 래퍼. 이벤트루프가 없는 스레드에서만 호출할 것."""
    asyncio.run(notify(text))
