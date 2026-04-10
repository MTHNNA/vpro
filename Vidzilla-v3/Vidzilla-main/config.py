import os
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
TEMP_DIRECTORY  = os.path.join(BASE_DIR, "temp_videos")
COOKIES_FILE    = os.path.join(BASE_DIR, "cookies.txt")
COOKIES_ENABLED = os.path.exists(COOKIES_FILE)

# ─── Bot settings ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_MODE  = os.getenv("BOT_MODE", "polling").strip().lower()

# ─── Server ───────────────────────────────────────────────────────────────────
PORT = int(os.getenv("PORT", "7860"))
HOST = os.getenv("HOST", "0.0.0.0")

# ─── Webhook ──────────────────────────────────────────────────────────────────
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL  = os.getenv("WEBHOOK_URL", "")

# ─── MongoDB ──────────────────────────────────────────────────────────────────
MONGODB_URI              = os.getenv("MONGODB_URI")
MONGODB_DB_NAME          = os.getenv("MONGODB_DB_NAME", "vidzilla")
MONGODB_USERS_COLLECTION = os.getenv("MONGODB_USERS_COLLECTION", "users")

# ─── Admin ────────────────────────────────────────────────────────────────────
ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(","))))

# ─── Validation ───────────────────────────────────────────────────────────────
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is not set!")

if BOT_MODE not in {"webhook", "polling"}:
    import logging
    logging.warning("⚠️ Unknown BOT_MODE=%s. Falling back to 'polling'.", BOT_MODE)
    BOT_MODE = "polling"

if BOT_MODE == "webhook" and not WEBHOOK_URL:
    raise ValueError("❌ WEBHOOK_URL is required when BOT_MODE=webhook")

if not MONGODB_URI:
    import logging
    logging.warning("⚠️ MONGODB_URI is not set — database features will be disabled.")

# ─── Telegram limits ──────────────────────────────────────────────────────────
TELEGRAM_VIDEO_LIMIT_MB = 50
TELEGRAM_FILE_LIMIT_MB  = 2000

# ─── Supported platforms ──────────────────────────────────────────────────────
PLATFORM_IDENTIFIERS = {
    # YouTube
    "youtube.com/shorts"    : "YouTube",
    "youtube.com/live"      : "YouTube",
    "youtube.com/clip"      : "YouTube",
    "youtube.com"           : "YouTube",
    "youtu.be"              : "YouTube",
    "music.youtube.com"     : "YouTube",
    # Instagram
    "instagram.com/reel"    : "Instagram",
    "instagram.com/reels"   : "Instagram",
    "instagram.com/p/"      : "Instagram",
    "instagram.com/tv/"     : "Instagram",
    "instagram.com/stories" : "Instagram",
    "instagram.com"         : "Instagram",
    # TikTok
    "vm.tiktok.com"         : "TikTok",
    "vt.tiktok.com"         : "TikTok",
    "tiktok.com"            : "TikTok",
    # Facebook
    "facebook.com"          : "Facebook",
    "fb.com"                : "Facebook",
    "fb.watch"              : "Facebook",
    "m.facebook.com"        : "Facebook",
    # Twitter / X
    "twitter.com"           : "Twitter",
    "x.com"                 : "Twitter",
    "t.co"                  : "Twitter",
    "fxtwitter.com"         : "Twitter",
    # Pinterest
    "pinterest.com"         : "Pinterest",
    "pinterest.co.uk"       : "Pinterest",
    "pin.it"                : "Pinterest",
    # Reddit
    "reddit.com"            : "Reddit",
    "redd.it"               : "Reddit",
    "v.redd.it"             : "Reddit",
    # Vimeo
    "vimeo.com"             : "Vimeo",
    # Dailymotion
    "dailymotion.com"       : "Dailymotion",
    "dai.ly"                : "Dailymotion",
    # Twitch
    "clips.twitch.tv"       : "Twitch",
    "twitch.tv"             : "Twitch",
    # Snapchat
    "snapchat.com/spotlight": "Snapchat",
    "snapchat.com"          : "Snapchat",
    "t.snapchat.com"        : "Snapchat",
    # Threads
    "threads.net"           : "Threads",
    # LinkedIn
    "linkedin.com"          : "LinkedIn",
    "lnkd.in"               : "LinkedIn",
    # Streamable
    "streamable.com"        : "Streamable",
    # Bilibili
    "bilibili.com"          : "Bilibili",
    "b23.tv"                : "Bilibili",
    # SoundCloud
    "soundcloud.com"        : "SoundCloud",
    "on.soundcloud.com"     : "SoundCloud",
    # Google Drive
    "drive.google.com"      : "GoogleDrive",
    # Dropbox
    "dropbox.com"           : "Dropbox",
    "dl.dropboxusercontent.com": "Dropbox",
    # Others
    "coub.com"              : "Coub",
    "ok.ru"                 : "Odnoklassniki",
    "vk.com"                : "VK",
}

# ─── Platform emoji ───────────────────────────────────────────────────────────
PLATFORM_EMOJI = {
    "YouTube"       : "▶️",
    "Instagram"     : "📸",
    "TikTok"        : "🎵",
    "Facebook"      : "👥",
    "Twitter"       : "🐦",
    "Pinterest"     : "📌",
    "Reddit"        : "🤖",
    "Vimeo"         : "🎞️",
    "Dailymotion"   : "📹",
    "Twitch"        : "🎮",
    "Snapchat"      : "👻",
    "Threads"       : "🧵",
    "LinkedIn"      : "💼",
    "Streamable"    : "📡",
    "Bilibili"      : "🅱️",
    "SoundCloud"    : "🎧",
    "GoogleDrive"   : "💾",
    "Dropbox"       : "📦",
    "Coub"          : "🔄",
    "Odnoklassniki" : "🌐",
    "VK"            : "🌐",
}

URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')

def extract_url(text: str) -> Optional[str]:
    m = URL_PATTERN.search(text)
    return m.group(0) if m else None

def get_platform_emoji(platform: str) -> str:
    return PLATFORM_EMOJI.get(platform, "🌐")
