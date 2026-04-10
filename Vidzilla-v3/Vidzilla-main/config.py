import os
import re
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

BASE_DIR        = os.path.dirname(os.path.abspath(__file__))
TEMP_DIRECTORY  = os.path.join(BASE_DIR, "temp_videos")
COOKIES_FILE    = os.path.join(BASE_DIR, "cookies.txt")
COOKIES_ENABLED = os.path.exists(COOKIES_FILE)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_MODE  = os.getenv("BOT_MODE", "polling").strip().lower()

PORT = int(os.getenv("PORT", "7860"))
HOST = os.getenv("HOST", "0.0.0.0")

WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
WEBHOOK_URL  = os.getenv("WEBHOOK_URL", "")

MONGODB_URI              = os.getenv("MONGODB_URI")
MONGODB_DB_NAME          = os.getenv("MONGODB_DB_NAME")
MONGODB_USERS_COLLECTION = os.getenv("MONGODB_USERS_COLLECTION")

ADMIN_IDS = list(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(","))))

# ─── Telegram limits ──────────────────────────────────────────────────────────
TELEGRAM_VIDEO_LIMIT_MB = 50
TELEGRAM_FILE_LIMIT_MB  = 2000   # Telegram Premium / Bot API limit

# ─── Supported platforms (ordered: specific paths before domain) ──────────────
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
    # Threads (Meta)
    "threads.net"           : "Threads",
    # LinkedIn
    "linkedin.com"          : "LinkedIn",
    "lnkd.in"               : "LinkedIn",
    # Streamable
    "streamable.com"        : "Streamable",
    # Bilibili
    "bilibili.com"          : "Bilibili",
    "b23.tv"                : "Bilibili",
    # SoundCloud (audio)
    "soundcloud.com"        : "SoundCloud",
    "on.soundcloud.com"     : "SoundCloud",
    # Google Drive
    "drive.google.com"      : "GoogleDrive",
    # Dropbox
    "dropbox.com"           : "Dropbox",
    "dl.dropboxusercontent.com": "Dropbox",
    # Generic direct links
    "coub.com"              : "Coub",
    "ok.ru"                 : "Odnoklassniki",
    "vk.com"                : "VK",
}

# Human-readable emoji per platform
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
