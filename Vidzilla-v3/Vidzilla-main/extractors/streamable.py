"""Streamable extractor"""
import re
from typing import Optional
from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

STREAMABLE_ID = re.compile(r'streamable\.com/([A-Za-z0-9]+)')

class StreamableExtractor(BaseExtractor):
    async def extract(self, url: str) -> Optional[VideoResult]:
        m = STREAMABLE_ID.search(url)
        if not m:
            return None
        vid = m.group(1)
        data = await self.fetch_json(
            f"https://api.streamable.com/videos/{vid}",
            headers={"User-Agent": GENERIC_USER_AGENT},
        )
        if not data:
            return None
        files = data.get("files", {})
        for quality in ["mp4", "mp4-mobile"]:
            f = files.get(quality, {})
            if f.get("url"):
                video_url = f["url"]
                if not video_url.startswith("http"):
                    video_url = "https:" + video_url
                return VideoResult(url=video_url, filename=f"streamable_{vid}.mp4")
        return None
