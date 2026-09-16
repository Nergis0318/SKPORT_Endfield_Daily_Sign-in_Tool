"""httpx 기반 텔레그램/디스코드 알림. 무자격 스킵, 무예외."""

import asyncio
import html
import os

import httpx

from app import state


async def send_telegram(
    bot_token: str, chat_id: str, text: str, mention_id: str = "", client=None
) -> bool:
    if not bot_token or not chat_id:
        return False
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=15)
    try:
        data = {"chat_id": chat_id, "text": text}
        if str(mention_id).isdigit():
            # 보이지 않는 멘션(tg://user): 실제 알림은 가고 본문에는 표식만 남는다.
            data["text"] = (
                f'<a href="tg://user?id={mention_id}">\U0001f514</a> {html.escape(text)}'
            )
            data["parse_mode"] = "HTML"
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[warn] telegram failed: {e}", flush=True)
        return False
    finally:
        if owned:
            await client.aclose()


async def send_discord(webhook_url: str, text: str, client=None) -> bool:
    if not webhook_url:
        return False
    owned = client is None
    if owned:
        client = httpx.AsyncClient(timeout=15)
    try:
        resp = await client.post(webhook_url, json={"content": text})
        return resp.status_code in (200, 204)
    except Exception as e:
        print(f"[warn] discord failed: {e}", flush=True)
        return False
    finally:
        if owned:
            await client.aclose()


async def notify(text: str) -> None:
    s = state.state["settings"]
    if s.get("telegram"):
        await send_telegram(
            s.get("telegram_bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            s.get("telegram_chat_id") or os.environ.get("TELEGRAM_CHAT_ID", ""),
            text,
            s.get("telegram_mention_id") or os.environ.get("TELEGRAM_MENTION_ID", ""),
        )
    if s.get("discord"):
        await send_discord(
            s.get("discord_webhook_url") or os.environ.get("DISCORD_WEBHOOK_URL", ""),
            text,
        )


def notify_sync(text: str) -> None:
    """Executor 스레드용 동기 래퍼. 이벤트루프가 없는 스레드에서만 호출할 것."""
    asyncio.run(notify(text))
