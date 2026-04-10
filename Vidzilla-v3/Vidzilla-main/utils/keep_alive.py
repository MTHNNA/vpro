"""
keep_alive.py — يمنع Render/Koyeb من إيقاف البوت
يرسل ping لنفسه كل 10 دقائق
"""
import asyncio
import logging
import os
import aiohttp

logger = logging.getLogger(__name__)

# رابط التطبيق — يُقرأ تلقائياً من متغير البيئة
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")


async def _ping_loop():
    """يرسل GET لنفسه كل 10 دقائق."""
    if not RENDER_URL:
        logger.info("[KeepAlive] RENDER_EXTERNAL_URL غير محدد — لن يعمل الـ ping")
        return

    url = f"{RENDER_URL}/health"
    logger.info(f"[KeepAlive] سيبدأ الـ ping لـ {url} كل 10 دقائق")

    await asyncio.sleep(60)  # انتظر دقيقة بعد البدء

    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    logger.info(f"[KeepAlive] ping → {r.status}")
        except Exception as e:
            logger.warning(f"[KeepAlive] ping فشل: {e}")

        await asyncio.sleep(600)  # كل 10 دقائق


def start_keep_alive():
    """استدعِ هذه الدالة مرة واحدة عند بدء البوت."""
    asyncio.ensure_future(_ping_loop())
