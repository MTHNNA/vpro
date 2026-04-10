"""Google Drive extractor — direct download links"""
import re
from typing import Optional
from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

FILE_ID_PATTERNS = [
    re.compile(r'drive\.google\.com/file/d/([A-Za-z0-9_-]+)'),
    re.compile(r'drive\.google\.com/open\?id=([A-Za-z0-9_-]+)'),
    re.compile(r'id=([A-Za-z0-9_-]+)'),
]

class GoogleDriveExtractor(BaseExtractor):
    def _extract_file_id(self, url: str) -> Optional[str]:
        for p in FILE_ID_PATTERNS:
            m = p.search(url)
            if m:
                return m.group(1)
        return None

    async def extract(self, url: str) -> Optional[VideoResult]:
        file_id = self._extract_file_id(url)
        if not file_id:
            return None
        # Use direct download URL
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
        self.logger.info(f"GoogleDrive: file_id={file_id}")
        return VideoResult(
            url=download_url,
            filename=f"gdrive_{file_id}.mp4",
            headers={
                "User-Agent": GENERIC_USER_AGENT,
                "Accept": "*/*",
            }
        )
