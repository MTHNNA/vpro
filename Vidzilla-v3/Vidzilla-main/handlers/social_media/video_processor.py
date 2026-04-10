"""
video_processor.py — Ultra-fast download + send engine
Supports: single video, single photo, carousel/slideshow, audio extraction
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
    FSInputFile, InputMediaPhoto, InputMediaVideo,
    InputMediaAudio, InlineKeyboardMarkup, InlineKeyboardButton, Message,
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

# ─── UI helpers ───────────────────────────────────────────────────────────────
def progress_bar(pct: float, width: int = 10) -> str:
    filled = int(width * pct / 100)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {pct:.0f}%"

def msg_downloading(platform: str, pct: float = 0) -> str:
    return f"{get_platform_emoji(platform)} *{platform}*\n⬇️ تحميل... {progress_bar(pct)}"

def msg_uploading(size_mb: float) -> str:
    return f"📤 إرسال `{size_mb:.1f} MB`..."

def msg_done(size_mb: float, elapsed: float) -> str:
    return f"✅ تم! `{size_mb:.1f} MB` في `{elapsed:.1f}s`"

def msg_done_multi(count: int, elapsed: float) -> str:
    return f"✅ تم إرسال {count} ملف في `{elapsed:.1f}s`"

def msg_error(reason: str) -> str:
    return f"❌ {reason}"

def msg_extracting_audio() -> str:
    return "🎵 جاري استخراج الصوت..."

def msg_done_audio(elapsed: float) -> str:
    return f"🎧 تم استخراج الصوت! في `{elapsed:.1f}s`"

# ─── Error classifier ─────────────────────────────────────────────────────────
def classify_error(e: Exception) -> str:
    s = str(e).lower()
    if "private"   in s: return "المحتوى خاص 🔒"
    if "login"     in s or "cookie" in s: return "يتطلب تسجيل دخول 🔑"
    if "not found" in s or "404"    in s or "deleted" in s: return "الفيديو محذوف ❌"
    if "age-restricted" in s or "confirm your age" in s or "age gate" in s: return "محتوى مقيد للعمر 🔞"
    if "geo"       in s or "country" in s: return "غير متاح في هذه المنطقة 🌍"
    if "copyright" in s or "dmca"   in s: return "محجوب بسبب حقوق الملكية 🚫"
    if "rate"      in s or "429"    in s: return "طلبات كثيرة، انتظر دقيقة ⏳"
    if "timeout"   in s or "timed"  in s: return "انتهت المهلة، حاول مجدداً ⏳"
    if "no video"  in s or "no media" in s: return "المنشور لا يحتوي فيديو 📝"
    return f"فشل التحميل: {str(e)[:80]}"

# ─── File utils ───────────────────────────────────────────────────────────────
def file_size_mb(path: str) -> float:
    try:   return os.path.getsize(path) / (1024 * 1024)
    except: return 0.0

def find_file(base: str) -> Optional[str]:
    for ext in [".mp4", ".webm", ".mkv", ".avi", ".mov", ".flv",
                ".m4v", ".mp3", ".m4a", ".opus", ".jpg", ".jpeg", ".png"]:
        p = base + ext
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p
    return None

def new_temp_path(platform: str, user_id: int, ext: str = "%(ext)s") -> str:
    uid = str(uuid.uuid4())[:8]
    return os.path.join(TEMP_DIRECTORY, f"{platform.lower()}_{user_id}_{uid}.{ext}")

# ─── yt-dlp options ───────────────────────────────────────────────────────────
def ytdlp_opts(output: str, platform: str, audio_only: bool = False) -> dict:
    opts = {
        "outtmpl"                      : output,
        "quiet"                        : True,
        "no_color"                     : True,
        "noprogress"                   : True,
        "geo_bypass"                   : True,
        "nocheckcertificate"           : True,
        "socket_timeout"               : 30,
        "retries"                      : 3,
        "fragment_retries"             : 5,
        "concurrent_fragment_downloads": 8,
        "http_headers"                 : {"User-Agent": get_random_user_agent()},
        "writeinfojson"                : False,
        "writesubtitles"               : False,
        "writethumbnail"               : False,
        "postprocessors"               : [],
        "extractor_args"               : {
            "youtube" : {"player_client": ["ios", "android", "web"]},
            "tiktok"  : {"api_hostname" : ["api22-normal-c-useast2a.tiktokv.com", "api19-normal-c-useast1a.tiktokv.com"]},
        },
    }
    if COOKIES_ENABLED:
        opts["cookiefile"] = COOKIES_FILE

    if audio_only:
        opts["format"] = "bestaudio/best"
        opts["postprocessors"].append({
            "key"             : "FFmpegExtractAudio",
            "preferredcodec"  : "mp3",
            "preferredquality": "320",
        })
        return opts

    if platform == "YouTube":
        opts["format"] = (
            "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]"
            "/bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]"
            "/best[ext=mp4][height<=1080]/best[ext=mp4]/best"
        )
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"].append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})
    elif platform == "Instagram":
        opts["format"] = "best[ext=mp4]/best"
        opts["http_headers"] = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15",
            "Accept": "*/*",
        }
    elif platform == "SoundCloud":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"].append({
            "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320",
        })
    else:
        opts["format"] = "best[ext=mp4][filesize<50M]/best[ext=mp4]/best"

    return opts


# ─── Single file downloader ───────────────────────────────────────────────────
async def _download_one_url(session: aiohttp.ClientSession, url: str,
                             dest: str, headers: dict) -> bool:
    """Stream download a direct URL to dest file."""
    try:
        async with session.get(url, headers=headers,
                               timeout=aiohttp.ClientTimeout(total=90)) as resp:
            if resp.status != 200:
                return False
            downloaded = 0
            limit = TELEGRAM_VIDEO_LIMIT_MB * 1024 * 1024
            with open(dest, "wb") as f:
                async for chunk in resp.content.iter_chunked(256 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded > limit:
                        os.unlink(dest)
                        return False
        return os.path.exists(dest) and os.path.getsize(dest) > 0
    except Exception:
        return False


# ─── Main Downloader ──────────────────────────────────────────────────────────
class VideoDownloader:
    def __init__(self):
        os.makedirs(TEMP_DIRECTORY, exist_ok=True)

    # ── Direct extractor (fastest path) ─────────────────────────────────────
    async def _try_direct(self, url: str, platform: str,
                           user_id: int) -> Optional[dict]:
        """
        Returns dict:
          {"type": "single", "path": str}
          {"type": "carousel", "items": [(path, is_video), ...]}
        """
        try:
            session   = await get_session()
            extractor = get_extractor(platform, session)
            if not extractor:
                return None

            result = await extractor.extract(url)
            if not result:
                return None

            ua = get_random_user_agent()

            # ── Carousel / slideshow ────────────────────────────────────────
            if result.carousel and len(result.carousel) > 1:
                logger.info(f"[Direct] {platform} → carousel {len(result.carousel)} items")
                items_out = []
                # Download all items concurrently
                tasks = []
                paths = []
                for item in result.carousel:
                    ext  = "mp4" if item.is_video else "jpg"
                    dest = new_temp_path(platform, user_id, ext)
                    paths.append((dest, item.is_video))
                    hdrs = dict(item.headers or {})
                    if not any(k.lower() == "user-agent" for k in hdrs):
                        hdrs["User-Agent"] = ua
                    tasks.append(_download_one_url(session, item.url, dest, hdrs))

                results = await asyncio.gather(*tasks, return_exceptions=True)
                for (dest, is_video), ok in zip(paths, results):
                    if ok is True and os.path.exists(dest):
                        items_out.append((dest, is_video))

                if items_out:
                    return {"type": "carousel", "items": items_out}
                return None

            # ── Single file ─────────────────────────────────────────────────
            if not result.url:
                return None

            ext  = "jpg" if result.is_photo else "mp4"
            dest = new_temp_path(platform, user_id, ext)
            hdrs = dict(result.headers or {})
            if not any(k.lower() == "user-agent" for k in hdrs):
                hdrs["User-Agent"] = ua

            ok = await _download_one_url(session, result.url, dest, hdrs)
            if ok:
                logger.info(f"[Direct] {platform} → {file_size_mb(dest):.1f}MB")
                return {"type": "single", "path": dest}

        except Exception as e:
            logger.debug(f"[Direct] {platform} failed: {e}")
        return None

    # ── yt-dlp fallback ──────────────────────────────────────────────────────
    async def _try_ytdlp(self, url: str, platform: str,
                          user_id: int, audio_only: bool = False) -> Optional[str]:
        out_tmpl = new_temp_path(platform, user_id, "%(ext)s")
        base     = out_tmpl.replace(".%(ext)s", "")
        opts     = ytdlp_opts(out_tmpl, platform, audio_only)
        last_err = None

        formats = [opts["format"], "best[ext=mp4]/best", "worst"] if not audio_only else [opts["format"]]

        for fmt in formats:
            opts["format"] = fmt
            try:
                def run():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                await asyncio.get_event_loop().run_in_executor(None, run)
                path = find_file(base)
                if path:
                    logger.info(f"[yt-dlp] {platform} {'audio' if audio_only else 'video'} → {file_size_mb(path):.1f}MB")
                    return path
            except yt_dlp.utils.DownloadError as e:
                last_err = e
                if any(x in classify_error(e) for x in ["خاص", "محذوف", "حقوق"]):
                    break
            except Exception as e:
                last_err = e
            # Clean partial
            for ext in [".mp4", ".webm", ".mkv", ".part", ".ytdl", ".mp3"]:
                p = base + ext
                if os.path.exists(p):
                    try: os.unlink(p)
                    except: pass

        if last_err:
            raise last_err
        raise Exception("All download attempts failed")

    # ── Audio extraction from local file ────────────────────────────────────
    async def _extract_audio_from_file(self, video_path: str) -> Optional[str]:
        """Use ffmpeg to extract MP3 from an already-downloaded video file."""
        out = video_path.rsplit(".", 1)[0] + "_audio.mp3"
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            out, "-loglevel", "error"
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 0:
                logger.info(f"[Audio] extracted MP3: {file_size_mb(out):.1f}MB")
                return out
            else:
                logger.warning(f"[Audio] ffmpeg error: {stderr.decode()[:200]}")
        except Exception as e:
            logger.warning(f"[Audio] extraction failed: {e}")
        return None

    # ── Main entry ────────────────────────────────────────────────────────────
    async def download(self, url: str, platform: str,
                       user_id: int, audio_only: bool = False,
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


# ─── Telegram sender ──────────────────────────────────────────────────────────
async def send_single(bot: Bot, chat_id: int, path: str,
                       platform: str, reply_to: int = None):
    """Send a single file (video/photo/audio) with fallback."""
    is_audio = path.endswith((".mp3", ".m4a", ".opus", ".ogg"))
    is_photo = path.endswith((".jpg", ".jpeg", ".png", ".webp"))

    if is_audio:
        fname = f"{platform.lower()}_audio.mp3"
        await bot.send_audio(
            chat_id=chat_id,
            audio=FSInputFile(path, filename=fname),
        )
        return

    if is_photo:
        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(path))
        return

    # Video: try as streamable video first, then document
    video_msg = None
    try:
        video_msg = await bot.send_video(
            chat_id=chat_id,
            video=FSInputFile(path),
            supports_streaming=True,
            reply_to_message_id=reply_to,
        )
    except Exception as e:
        logger.warning(f"send_video failed: {e}")

    try:
        await bot.send_document(
            chat_id=chat_id,
            document=FSInputFile(path, filename=f"{platform.lower()}_video.mp4"),
            reply_to_message_id=video_msg.message_id if video_msg else reply_to,
            disable_content_type_detection=True,
        )
    except Exception as e:
        logger.warning(f"send_document failed: {e}")
        if not video_msg:
            raise


async def send_carousel(bot: Bot, chat_id: int,
                         items: list, platform: str):
    """
    Send carousel as Telegram media group (max 10 per group).
    items = [(path, is_video), ...]
    """
    CHUNK = 10
    for i in range(0, len(items), CHUNK):
        chunk = items[i:i+CHUNK]
        media_group = []
        for path, is_video in chunk:
            if is_video:
                media_group.append(InputMediaVideo(media=FSInputFile(path)))
            else:
                media_group.append(InputMediaPhoto(media=FSInputFile(path)))
        try:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            logger.warning(f"media_group failed: {e}")
            # Fallback: send individually
            for path, is_video in chunk:
                try:
                    if is_video:
                        await bot.send_video(chat_id=chat_id, video=FSInputFile(path))
                    else:
                        await bot.send_photo(chat_id=chat_id, photo=FSInputFile(path))
                except Exception as ex:
                    logger.warning(f"individual send failed: {ex}")
        # Small delay between chunks to avoid flood
        if i + CHUNK < len(items):
            await asyncio.sleep(0.5)


# ─── Inline keyboard for video options ────────────────────────────────────────
def make_options_keyboard(platform: str) -> InlineKeyboardMarkup:
    """Keyboard shown after video is sent with option to extract audio."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎵 استخراج الصوت MP3", callback_data=f"audio_done"),
    ]])


# ─── Main pipeline ────────────────────────────────────────────────────────────
async def process_social_media_video(
    message: Message,
    bot: Bot,
    url: str,
    platform: str,
    progress_msg=None,
    audio_only: bool = False,
):
    downloader = VideoDownloader()
    t_start    = time.monotonic()
    all_paths  = []

    async def update_progress(pct: float):
        if progress_msg:
            if audio_only:
                await safe_edit_message(progress_msg, msg_extracting_audio())
            else:
                await safe_edit_message(progress_msg, msg_downloading(platform, pct))

    try:
        if progress_msg:
            await safe_edit_message(
                progress_msg,
                msg_extracting_audio() if audio_only else msg_downloading(platform, 0),
            )

        result = await downloader.download(
            url, platform, message.from_user.id,
            audio_only=audio_only,
            progress_cb=update_progress,
        )

        elapsed = time.monotonic() - t_start

        # ── Carousel ────────────────────────────────────────────────────────
        if result["type"] == "carousel":
            items = result["items"]
            all_paths = [p for p, _ in items]
            total_mb  = sum(file_size_mb(p) for p in all_paths)

            if progress_msg:
                await safe_edit_message(progress_msg, msg_uploading(total_mb))

            await send_carousel(bot, message.chat.id, items, platform)

            if progress_msg:
                await safe_edit_message(progress_msg, msg_done_multi(len(items), elapsed))

        # ── Single file ──────────────────────────────────────────────────────
        else:
            path = result["path"]
            all_paths = [path]
            size_mb   = file_size_mb(path)

            if size_mb > TELEGRAM_VIDEO_LIMIT_MB and not audio_only:
                if progress_msg:
                    await safe_edit_message(progress_msg, f"⚠️ الملف كبير جداً `{size_mb:.1f} MB` (الحد ٥٠ MB)")
                return

            if progress_msg:
                await safe_edit_message(progress_msg, msg_uploading(size_mb))

            await send_single(bot, message.chat.id, path, platform)

            if audio_only:
                if progress_msg:
                    await safe_edit_message(progress_msg, msg_done_audio(elapsed))
            else:
                if progress_msg:
                    await safe_edit_message(progress_msg, msg_done(size_mb, elapsed))

        logger.info(f"✅ {platform} | {elapsed:.1f}s | audio_only={audio_only}")

    except yt_dlp.utils.DownloadError as e:
        err = msg_error(classify_error(e))
        if progress_msg: await safe_edit_message(progress_msg, err)
        else: await bot.send_message(message.chat.id, err)

    except Exception as e:
        s   = str(e).lower()
        err = msg_error("انتهت المهلة ⏳" if "timeout" in s or "timed" in s else classify_error(e))
        logger.error(f"Error [{platform}]: {e}")
        if progress_msg: await safe_edit_message(progress_msg, err)
        else: await bot.send_message(message.chat.id, err)

    finally:
        for p in all_paths:
            if p and os.path.exists(p):
                try: os.unlink(p)
                except: pass
        try: cleanup_temp_directory()
        except: pass


# ─── Audio extraction pipeline ────────────────────────────────────────────────
async def process_audio_extraction(
    message: Message,
    bot: Bot,
    url: str,
    platform: str,
    progress_msg=None,
):
    """Download video then extract MP3 audio from it."""
    await process_social_media_video(
        message, bot, url, platform, progress_msg, audio_only=True
    )


# ─── Platform detector ────────────────────────────────────────────────────────
async def detect_platform_and_process(
    message: Message,
    bot: Bot,
    url: str,
    progress_msg=None,
    audio_only: bool = False,
) -> bool:
    for domain, platform in PLATFORM_IDENTIFIERS.items():
        if domain in url:
            await process_social_media_video(
                message, bot, url, platform, progress_msg, audio_only=audio_only
            )
            return True
    return False
