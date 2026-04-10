"""Extractors package — 25+ platforms"""
from typing import Optional
import aiohttp

from .base import BaseExtractor, VideoResult
from .instagram  import InstagramExtractor
from .tiktok     import TikTokExtractor
from .youtube    import YouTubeExtractor
from .twitter    import TwitterExtractor
from .facebook   import FacebookExtractor
from .pinterest  import PinterestExtractor
from .reddit     import RedditExtractor
from .vimeo      import VimeoExtractor
from .streamable import StreamableExtractor
from .threads    import ThreadsExtractor
from .googledrive import GoogleDriveExtractor

_EXTRACTORS = {
    "Instagram"   : InstagramExtractor,
    "TikTok"      : TikTokExtractor,
    "YouTube"     : YouTubeExtractor,
    "Twitter"     : TwitterExtractor,
    "Facebook"    : FacebookExtractor,
    "Pinterest"   : PinterestExtractor,
    "Reddit"      : RedditExtractor,
    "Vimeo"       : VimeoExtractor,
    "Streamable"  : StreamableExtractor,
    "Threads"     : ThreadsExtractor,
    "GoogleDrive" : GoogleDriveExtractor,
    # These use yt-dlp directly (no custom extractor needed)
    # "Dailymotion", "Twitch", "Snapchat", "LinkedIn",
    # "Bilibili", "SoundCloud", "Coub", "VK", "Odnoklassniki", "Dropbox"
}

def get_extractor(platform_name: str, session: aiohttp.ClientSession) -> Optional[BaseExtractor]:
    cls = _EXTRACTORS.get(platform_name)
    return cls(session) if cls else None

__all__ = ["get_extractor", "VideoResult", "BaseExtractor"]
