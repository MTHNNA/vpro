"""Vimeo extractor — uses oembed API"""
import re
from typing import Optional
from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

VIMEO_ID = re.compile(r'vimeo\.com/(?:video/)?(\d+)')

class VimeoExtractor(BaseExtractor):
    async def extract(self, url: str) -> Optional[VideoResult]:
        m = VIMEO_ID.search(url)
        if not m:
            return None
        video_id = m.group(1)
        data = await self.fetch_json(
            f"https://vimeo.com/api/v2/video/{video_id}.json",
            headers={"User-Agent": GENERIC_USER_AGENT},
        )
        if not data or not isinstance(data, list):
            return None
        video = data[0]
        # Vimeo requires yt-dlp for actual stream URLs, return None to fall through
        self.logger.info(f"Vimeo: delegating {video_id} to yt-dlp")
        return None
