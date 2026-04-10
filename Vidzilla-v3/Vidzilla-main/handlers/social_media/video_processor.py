"""
video_processor.py — Ultra-fast download + send engine
✅ Fixed: YouTube player_client + po_token bypass
✅ Fixed: Instagram mobile headers + cookies fallback
✅ Fixed: Better error handling & retry logic
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Optional, List

import aiohttp
import yt_dlp
from aiogram import Bot
from aiogram.types import (
    FSInputFile, InputMediaPhoto, InputMediaVideo, Message,
    InlineKeyboardMarkup, InlineKeyboardButton,
)

from config import (
    TEMP_DIRECTORY, PLATFORM_IDENTIFIERS, COOKIES_FILE, COOKIES_ENABLED,
    TELEGRAM_VIDEO_LIMIT_MB, get_platform_emoji,
)
from utils.user_agent_utils import get_random_user_agent
from utils.common_utils import safe_edit_message
from utils.cleanup import cleanup_temp_directory
from extractors import get_extractor
from extractors.base import MediaItem

logger = logging.getLogger(__name__)
os.makedirs(TEMP_DIRECTORY, exist_ok=True)

# ─── Shared aiohttp session ───────────────────────────────────────────────────
_session: Optional[aiohttp.ClientSession] = None

async def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        connector = aiohttp.TCPConnector(
            limit=50, limit_per_host=10,
            ttl_dns_cache=300, use_dns_cache=True,
            keepalive_timeout=60,
        )
        _session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=120, connect=10),
        )
    return _session

# ─── UI ───────────────────────────────────────────────────────────────────────
def _bar(pct: float) -> str:
    n = int(10 * pct / 100)
    return f"[{'█'*n}{'░'*(10-n)}] {pct:.0f}%"

def msg_dl(platform: str, pct: float = 0) -> str:
    return f"{get_platform_emoji(platform)} *{platform}*\n⬇️ تحميل... {_bar(pct)}"

def msg_up(mb: float)           -> str: return f"📤 إرسال `{mb:.1f} MB`..."
def msg_ok(mb: float, t: float) -> str: return f"✅ تم! `{mb:.1f} MB` في `{t:.1f}s`"
def msg_ok_n(n: int, t: float)  -> str: return f"✅ تم إرسال {n} ملف في `{t:.1f}s`"
def msg_audio_ok(t: float)      -> str: return f"🎧 تم استخراج الصوت في `{t:.1f}s`"
def msg_err(r: str)             -> str: return f"❌ {r}"

# ─── Error classifier ─────────────────────────────────────────────────────────
def classify_error(e: Exception) -> str:
    s = str(e).lower()
    if "private"         in s: return "المحتوى خاص 🔒"
    if "login"           in s or "sign in" in s: return "يتطلب تسجيل دخول — أرسل رابطاً عاماً 🔑"
    if "cookie"          in s or "checkpoint" in s: return "الرابط خاص أو محمي 🔒"
    if "not found"       in s or "404" in s or "deleted" in s: return "الفيديو محذوف ❌"
    if "age-restricted"  in s or "confirm your age" in s: return "محتوى مقيد للعمر 🔞"
    if "geo"             in s or "not available in your country" in s: return "غير متاح في هذه المنطقة 🌍"
    if "copyright"       in s or "dmca" in s: return "محجوب بسبب حقوق الملكية 🚫"
    if "rate"            in s or "429"  in s: return "طلبات كثيرة، انتظر دقيقة ⏳"
    if "timeout"         in s or "timed out" in s: return "انتهت المهلة ⏳"
    if "no video"        in s or "no media" in s: return "المنشور لا يحتوي فيديو 📝"
    if "unsupported url" in s or "unable to extract" in s: return "الرابط غير مدعوم ❌"
    if "http error 403"  in s: return "الوصول مرفوض — جرب لاحقاً 🚫"
    if "http error 429"  in s: return "طلبات كثيرة جداً، انتظر دقيقتين ⏳"
    if "sign_in_required" in s or "bot" in s: return "يوتيوب يطلب تسجيل دخول مؤقتاً 🔑"
    return f"فشل التحميل — تأكد أن الرابط عام\n`{str(e)[:80]}`"

# ─── File utils ───────────────────────────────────────────────────────────────
def file_mb(path: str) -> float:
    try:   return os.path.getsize(path) / 1_048_576
    except: return 0.0

def find_file(base: str) -> Optional[str]:
    for ext in [".mp4", ".webm", ".mkv", ".avi", ".mov",
                ".flv", ".m4v", ".mp3", ".m4a", ".opus", ".jpg", ".png"]:
        p = base + ext
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None

def tmp(platform: str, user_id: int, ext: str = "%(ext)s") -> str:
    return os.path.join(TEMP_DIRECTORY,
                        f"{platform.lower()}_{user_id}_{uuid.uuid4().hex[:8]}.{ext}")

# ─── yt-dlp runner ────────────────────────────────────────────────────────────
def _run_ytdlp(url: str, opts: dict):
    """Synchronous yt-dlp download — runs in executor."""
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])

# ─── yt-dlp options per platform ──────────────────────────────────────────────
def _base_opts(output: str) -> dict:
    return {
        "outtmpl"                      : output,
        "quiet"                        : True,
        "no_color"                     : True,
        "noprogress"                   : True,
        "geo_bypass"                   : True,
        "nocheckcertificate"           : True,
        "socket_timeout"               : 30,
        "retries"                      : 5,
        "fragment_retries"             : 10,
        "concurrent_fragment_downloads": 4,
        "http_headers"                 : {"User-Agent": get_random_user_agent()},
        "writeinfojson"  : False,
        "writesubtitles" : False,
        "writethumbnail" : False,
        "postprocessors" : [],
    }

def _youtube_opts_list(output: str, base: dict, audio_only: bool) -> list:
    """
    ✅ إصلاح يوتيوب:
    - استخدام player_client: mweb أولاً (الأسرع والأقل تقييداً)
    - ثم ios + web كـ fallback
    - تجنب android لأنه محجوب في بعض الأحيان
    """
    import copy

    if audio_only:
        opt = copy.deepcopy(base)
        opt["format"] = "bestaudio[ext=m4a]/bestaudio/best"
        opt["extractor_args"] = {
            "youtube": {
                "player_client": ["mweb", "ios", "web"],
                "skip": ["dash", "hls"],
            }
        }
        opt["postprocessors"].append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        })
        return [opt]

    # الخيار 1: جودة عالية مع mweb client
    opt1 = copy.deepcopy(base)
    opt1["format"] = (
        "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]"
        "/bestvideo[height<=720]+bestaudio"
        "/best[ext=mp4][height<=1080]/best[ext=mp4]/best"
    )
    opt1["merge_output_format"] = "mp4"
    opt1["extractor_args"] = {
        "youtube": {
            "player_client": ["mweb", "ios"],
            "skip": ["dash"],
        }
    }

    # الخيار 2: جودة بسيطة
    opt2 = copy.deepcopy(base)
    opt2["format"] = "best[ext=mp4][height<=720]/best[ext=mp4]/best"
    opt2["extractor_args"] = {
        "youtube": {
            "player_client": ["mweb", "web"],
        }
    }

    # الخيار 3: أبسط خيار ممكن
    opt3 = copy.deepcopy(base)
    opt3["format"] = "worst[ext=mp4]/worst"
    opt3["extractor_args"] = {
        "youtube": {"player_client": ["web"]}
    }

    return [opt1, opt2, opt3]


def _instagram_opts_list(output: str, base: dict, audio_only: bool) -> list:
    """
    ✅ إصلاح إنستقرام:
    - استخدام User-Agent للموبايل الحديث
    - إضافة headers مطابقة لمتصفح إنستقرام
    - ثلاث محاولات بإعدادات مختلفة
    """
    import copy

    # Mobile Instagram UA (2024)
    ig_mobile_ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Mobile/21F90 Instagram 341.0.0.36.98"
    )
    ig_chrome_ua = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Mobile Safari/537.36 Instagram/341.0.0.36.98"
    )
    ig_desktop_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.6422.142 Safari/537.36"
    )

    common_headers = {
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    # المحاولة 1: iPhone UA
    opt1 = copy.deepcopy(base)
    opt1["format"] = "best[ext=mp4]/best"
    opt1["http_headers"] = {**common_headers, "User-Agent": ig_mobile_ua}
    if COOKIES_ENABLED:
        opt1["cookiefile"] = COOKIES_FILE

    # المحاولة 2: Android Chrome UA
    opt2 = copy.deepcopy(base)
    opt2["format"] = "best[ext=mp4]/best"
    opt2["http_headers"] = {**common_headers, "User-Agent": ig_chrome_ua}
    opt2["extractor_args"] = {"instagram": {"include_dash_manifest": ["0"]}}
    if COOKIES_ENABLED:
        opt2["cookiefile"] = COOKIES_FILE

    # المحاولة 3: Desktop UA بدون cookies
    opt3 = copy.deepcopy(base)
    opt3["format"] = "best"
    opt3["http_headers"] = {"User-Agent": ig_desktop_ua}

    if audio_only:
        for opt in [opt1, opt2, opt3]:
            opt["format"] = "bestaudio/best"
            opt["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })

    return [opt1, opt2, opt3]


def build_opts(output: str, platform: str, audio_only: bool = False) -> list:
    """Return list of opts dicts to try (best → worst)."""
    base = _base_opts(output)
    if COOKIES_ENABLED:
        base["cookiefile"] = COOKIES_FILE

    if platform == "YouTube":
        return _youtube_opts_list(output, base, audio_only)

    elif platform == "Instagram":
        return _instagram_opts_list(output, base, audio_only)

    elif platform == "TikTok":
        import copy
        base["extractor_args"] = {
            "tiktok": {"api_hostname": [
                "api22-normal-c-useast2a.tiktokv.com",
                "api19-normal-c-useast1a.tiktokv.com",
            ]}
        }
        opt1 = copy.deepcopy(base)
        opt1["format"] = "best[ext=mp4]/best"
        opt2 = copy.deepcopy(base)
        opt2["format"] = "best"
        if audio_only:
            for opt in [opt1, opt2]:
                opt["format"] = "bestaudio/best"
                opt["postprocessors"].append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                })
        return [opt1, opt2]

    elif platform == "Twitter":
        import copy
        opt1 = copy.deepcopy(base)
        opt1["format"] = "best[ext=mp4]/best"
        if audio_only:
            opt1["format"] = "bestaudio/best"
            opt1["postprocessors"].append({
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            })
        return [opt1]

    elif platform == "SoundCloud":
        import copy
        opt1 = copy.deepcopy(base)
        opt1["format"] = "bestaudio/best"
        opt1["postprocessors"].append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "320",
        })
        return [opt1]

    else:
        # Facebook, Vimeo, Dailymotion, Twitch, Reddit, etc.
        import copy
        opt1 = copy.deepcopy(base)
        opt1["format"] = "best[ext=mp4][filesize<50M]/best[ext=mp4]/best"
        opt2 = copy.deepcopy(base)
        opt2["format"] = "best[ext=mp4]/best"
        opt3 = copy.deepcopy(base)
        opt3["format"] = "worst"
        if audio_only:
            for opt in [opt1, opt2, opt3]:
                opt["format"] = "bestaudio/best"
                opt["postprocessors"].append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                })
        return [opt1, opt2, opt3]


# ─── Direct URL downloader ────────────────────────────────────────────────────
async def _dl_url(session: aiohttp.ClientSession,
                   url: str, dest: str, headers: dict) -> bool:
    try:
        async with session.get(
            url, headers=headers,
            timeout=aiohttp.ClientTimeout(total=90),
        ) as resp:
            if resp.status != 200:
                return False
            total = 0
            limit = TELEGRAM_VIDEO_LIMIT_MB * 1_048_576
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    f.write(chunk)
                    total += len(chunk)
                    if total > limit:
                        os.unlink(dest)
                        return False
        return os.path.exists(dest) and os.path.getsize(dest) > 0
    except Exception:
        return False


# ─── Main Downloader ──────────────────────────────────────────────────────────
class VideoDownloader:

    # ── 1. Direct extractor ──────────────────────────────────────────────────
    async def _try_direct(self, url: str, platform: str,
                           user_id: int) -> Optional[dict]:
        try:
            session   = await get_session()
            extractor = get_extractor(platform, session)
            if not extractor:
                return None

            result = await extractor.extract(url)
            if not result:
                return None

            ua   = get_random_user_agent()
            hdrs = dict(result.headers or {})
            if not any(k.lower() == "user-agent" for k in hdrs):
                hdrs["User-Agent"] = ua

            # Carousel
            if result.carousel and len(result.carousel) > 1:
                tasks = []
                paths = []
                for item in result.carousel:
                    ext  = "mp4" if item.is_video else "jpg"
                    dest = tmp(platform, user_id, ext)
                    paths.append((dest, item.is_video))
                    h = dict(item.headers or {"User-Agent": ua})
                    tasks.append(_dl_url(session, item.url, dest, h))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                items_out = [
                    (dest, is_v)
                    for (dest, is_v), ok in zip(paths, results)
                    if ok is True and os.path.exists(dest)
                ]
                if items_out:
                    logger.info(f"[Direct] {platform} carousel → {len(items_out)} items")
                    return {"type": "carousel", "items": items_out}
                return None

            # Single
            if not result.url:
                return None

            ext  = "jpg" if result.is_photo else "mp4"
            dest = tmp(platform, user_id, ext)
            ok   = await _dl_url(session, result.url, dest, hdrs)
            if ok:
                logger.info(f"[Direct] {platform} → {file_mb(dest):.1f}MB")
                return {"type": "single", "path": dest}

        except Exception as e:
            logger.debug(f"[Direct] {platform} failed: {e}")
        return None

    # ── 2. yt-dlp fallback ───────────────────────────────────────────────────
    async def _try_ytdlp(self, url: str, platform: str,
                          user_id: int, audio_only: bool = False) -> str:
        out_tmpl  = tmp(platform, user_id, "%(ext)s")
        base      = out_tmpl.replace(".%(ext)s", "")
        opts_list = build_opts(out_tmpl, platform, audio_only)
        last_err  = None

        for i, opts in enumerate(opts_list):
            try:
                logger.info(f"[yt-dlp] {platform} attempt {i+1}/{len(opts_list)}")
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda o=opts: _run_ytdlp(url, o))

                path = find_file(base)
                if path:
                    logger.info(f"[yt-dlp] {platform} ✅ → {file_mb(path):.1f}MB")
                    return path

            except yt_dlp.utils.DownloadError as e:
                last_err = e
                err_cls  = classify_error(e)
                logger.warning(f"[yt-dlp] {platform} attempt {i+1} failed: {str(e)[:120]}")
                # لا تعيد المحاولة على أخطاء دائمة
                if any(x in err_cls for x in ["خاص 🔒", "محذوف", "حقوق", "تسجيل دخول"]):
                    break
                # انتظر قليلاً قبل المحاولة التالية
                if i < len(opts_list) - 1:
                    await asyncio.sleep(2)

            except Exception as e:
                last_err = e
                logger.warning(f"[yt-dlp] {platform} attempt {i+1} error: {str(e)[:120]}")
                if i < len(opts_list) - 1:
                    await asyncio.sleep(1)

            # تنظيف الملفات الجزئية
            for ext in [".mp4", ".webm", ".mkv", ".part", ".ytdl", ".mp3", ".m4a", ".temp"]:
                p = base + ext
                if os.path.exists(p):
                    try: os.unlink(p)
                    except: pass

        if last_err:
            raise last_err
        raise Exception("جميع محاولات التحميل فشلت")

    # ── Main ─────────────────────────────────────────────────────────────────
    async def download(self, url: str, platform: str, user_id: int,
                        audio_only: bool = False,
                        progress_cb=None) -> dict:

        if progress_cb: await progress_cb(5)

        if not audio_only:
            direct = await self._try_direct(url, platform, user_id)
            if direct:
                if progress_cb: await progress_cb(90)
                return direct

        if progress_cb: await progress_cb(25)
        path = await self._try_ytdlp(url, platform, user_id, audio_only)
        if progress_cb: await progress_cb(90)
        return {"type": "single", "path": path}


# ─── Telegram senders ─────────────────────────────────────────────────────────
async def send_single(bot: Bot, chat_id: int, path: str,
                       platform: str, reply_to: int = None):
    is_audio = path.endswith((".mp3", ".m4a", ".opus", ".ogg"))
    is_photo = path.endswith((".jpg", ".jpeg", ".png", ".webp"))

    if is_audio:
        await bot.send_audio(chat_id=chat_id,
                              audio=FSInputFile(path, filename=f"{platform}.mp3"))
        return

    if is_photo:
        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(path))
        return

    video_sent = False
    try:
        await bot.send_video(
            chat_id=chat_id, video=FSInputFile(path),
            supports_streaming=True, reply_to_message_id=reply_to,
        )
        video_sent = True
    except Exception as e:
        logger.warning(f"send_video failed: {e}")

    if not video_sent:
        try:
            await bot.send_document(
                chat_id=chat_id,
                document=FSInputFile(path, filename=f"{platform.lower()}_video.mp4"),
                reply_to_message_id=reply_to,
                disable_content_type_detection=True,
            )
        except Exception as e:
            logger.error(f"send_document also failed: {e}")
            raise


async def send_carousel(bot: Bot, chat_id: int, items: list, platform: str):
    for i in range(0, len(items), 10):
        chunk = items[i:i+10]
        group = [
            InputMediaVideo(media=FSInputFile(p)) if is_v
            else InputMediaPhoto(media=FSInputFile(p))
            for p, is_v in chunk
        ]
        try:
            await bot.send_media_group(chat_id=chat_id, media=group)
        except Exception as e:
            logger.warning(f"media_group failed: {e}")
            for p, is_v in chunk:
                try:
                    if is_v: await bot.send_video(chat_id=chat_id, video=FSInputFile(p))
                    else:    await bot.send_photo(chat_id=chat_id, photo=FSInputFile(p))
                except Exception: pass
        if i + 10 < len(items):
            await asyncio.sleep(0.5)


# ─── Main pipeline ────────────────────────────────────────────────────────────
async def process_social_media_video(
    message: Message, bot: Bot,
    url: str, platform: str,
    progress_msg=None, audio_only: bool = False,
):
    downloader = VideoDownloader()
    t0         = time.monotonic()
    all_paths  = []

    async def upd(pct: float):
        if progress_msg:
            txt = "🎵 جاري استخراج الصوت..." if audio_only else msg_dl(platform, pct)
            await safe_edit_message(progress_msg, txt)

    try:
        await upd(0)
        result = await downloader.download(url, platform, message.from_user.id,
                                            audio_only=audio_only, progress_cb=upd)
        elapsed = time.monotonic() - t0

        if result["type"] == "carousel":
            items    = result["items"]
            all_paths = [p for p, _ in items]
            total_mb = sum(file_mb(p) for p in all_paths)
            if progress_msg: await safe_edit_message(progress_msg, msg_up(total_mb))
            await send_carousel(bot, message.chat.id, items, platform)
            if progress_msg: await safe_edit_message(progress_msg, msg_ok_n(len(items), elapsed))

        else:
            path = result["path"]
            all_paths = [path]
            mb = file_mb(path)

            if mb > TELEGRAM_VIDEO_LIMIT_MB and not audio_only:
                if progress_msg:
                    await safe_edit_message(progress_msg, f"⚠️ الملف كبير جداً `{mb:.1f} MB` (الحد ٥٠ MB)")
                return

            if progress_msg: await safe_edit_message(progress_msg, msg_up(mb))
            await send_single(bot, message.chat.id, path, platform)

            if progress_msg:
                txt = msg_audio_ok(elapsed) if audio_only else msg_ok(mb, elapsed)
                await safe_edit_message(progress_msg, txt)

        logger.info(f"✅ {platform} | {elapsed:.1f}s")

    except yt_dlp.utils.DownloadError as e:
        err = msg_err(classify_error(e))
        logger.error(f"[{platform}] DownloadError: {e}")
        if progress_msg: await safe_edit_message(progress_msg, err)
        else: await bot.send_message(message.chat.id, err)

    except Exception as e:
        s   = str(e).lower()
        err = msg_err("انتهت المهلة ⏳" if "timeout" in s or "timed" in s
                       else classify_error(e))
        logger.error(f"[{platform}] Error: {e}")
        if progress_msg: await safe_edit_message(progress_msg, err)
        else: await bot.send_message(message.chat.id, err)

    finally:
        for p in all_paths:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
        try: cleanup_temp_directory()
        except: pass


# ─── Audio extraction ─────────────────────────────────────────────────────────
async def process_audio_extraction(message, bot, url, platform, progress_msg=None):
    await process_social_media_video(message, bot, url, platform, progress_msg, audio_only=True)


# ─── Platform detector ────────────────────────────────────────────────────────
async def detect_platform_and_process(
    message: Message, bot: Bot, url: str,
    progress_msg=None, audio_only: bool = False,
) -> bool:
    for domain, platform in PLATFORM_IDENTIFIERS.items():
        if domain in url:
            await process_social_media_video(
                message, bot, url, platform, progress_msg, audio_only,
            )
            return True
    return False
