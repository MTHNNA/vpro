import aiohttp
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

GENERIC_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

@dataclass
class MediaItem:
    """Single item in a carousel/slideshow."""
    url: str
    filename: str
    is_video: bool = False          # True = video, False = image
    headers: Optional[Dict[str, str]] = None

@dataclass
class VideoResult:
    """Result of a video/media extraction."""
    url: str                                      # primary media URL
    filename: str                                 # suggested filename
    audio_url: Optional[str] = None               # separate audio stream (merge)
    thumbnail: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    filesize: Optional[int] = None
    is_photo: bool = False                        # single photo
    headers: Optional[Dict[str, str]] = None      # download headers
    carousel: Optional[List[MediaItem]] = None    # slideshow / album items
    # legacy compat
    picker: Optional[List[Dict[str, str]]] = None


class BaseExtractor:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session
        self.logger  = logging.getLogger(self.__class__.__name__)

    async def fetch(self, url, headers=None, method="GET",
                    data=None, allow_redirects=True, timeout=15):
        try:
            kwargs: Dict[str, Any] = {
                "headers": headers or {},
                "allow_redirects": allow_redirects,
                "timeout": aiohttp.ClientTimeout(total=timeout),
            }
            if data is not None:
                kwargs["data"] = data
            async with self.session.request(method, url, **kwargs) as resp:
                if resp.status != 200:
                    self.logger.warning(f"HTTP {resp.status} for {url}")
                    return None
                return await resp.text()
        except Exception as e:
            self.logger.warning(f"Fetch error for {url}: {e}")
            return None

    async def fetch_json(self, url, headers=None, method="GET",
                         data=None, timeout=15):
        try:
            kwargs: Dict[str, Any] = {
                "headers": headers or {},
                "timeout": aiohttp.ClientTimeout(total=timeout),
            }
            if data is not None:
                kwargs["data"] = data
            async with self.session.request(method, url, **kwargs) as resp:
                if resp.status != 200:
                    self.logger.warning(f"HTTP {resp.status} for {url}")
                    return None
                return await resp.json(content_type=None)
        except Exception as e:
            self.logger.warning(f"Fetch JSON error for {url}: {e}")
            return None

    async def resolve_redirect(self, url, headers=None):
        try:
            async with self.session.get(
                url,
                headers=headers or {"User-Agent": GENERIC_USER_AGENT},
                allow_redirects=True,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                return str(resp.url)
        except Exception as e:
            self.logger.warning(f"Redirect resolve error for {url}: {e}")
            return None

    async def extract(self, url: str) -> Optional[VideoResult]:
        raise NotImplementedError
