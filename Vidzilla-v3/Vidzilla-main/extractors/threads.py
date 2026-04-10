"""Threads (Meta) extractor — uses embed parsing"""
import re
import json
from typing import Optional
from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

THREADS_POST = re.compile(r'threads\.net/(?:@[^/]+/)?post/([A-Za-z0-9_-]+)')

EMBED_HEADERS = {
    "User-Agent": GENERIC_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

class ThreadsExtractor(BaseExtractor):
    async def extract(self, url: str) -> Optional[VideoResult]:
        m = THREADS_POST.search(url)
        if not m:
            return None
        post_id = m.group(1)
        # Try embed
        html = await self.fetch(
            f"https://www.threads.net/t/{post_id}/embed",
            headers=EMBED_HEADERS,
        )
        if not html:
            return None
        # Look for video URL
        video_m = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
        if video_m:
            try:
                video_url = json.loads(f'"{video_m.group(1)}"')
                return VideoResult(url=video_url, filename=f"threads_{post_id}.mp4")
            except Exception:
                pass
        # Look for image
        image_m = re.search(r'"display_url"\s*:\s*"([^"]+)"', html)
        if image_m:
            try:
                img_url = json.loads(f'"{image_m.group(1)}"')
                return VideoResult(url=img_url, filename=f"threads_{post_id}.jpg", is_photo=True)
            except Exception:
                pass
        return None
