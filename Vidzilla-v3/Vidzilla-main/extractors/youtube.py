"""
YouTube extractor — ported from Cobalt's youtube.js

Uses the Innertube API with iOS client context to bypass some restrictions.
POST https://www.youtube.com/youtubei/api/v1/player

✅ Updated: iOS client version bumped to 19.45.4
✅ Updated: API key refreshed
✅ Updated: Better format selection logic
"""

import re
import json
from typing import Optional

from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

# YouTube video ID patterns
YT_ID_PATTERN = re.compile(
    r'(?:youtube\.com/(?:watch\?v=|shorts/|embed/|v/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)

# ✅ iOS client محدّث (2025)
IOS_CLIENT = {
    "clientName": "IOS",
    "clientVersion": "19.45.4",
    "deviceMake": "Apple",
    "deviceModel": "iPhone16,2",
    "userAgent": "com.google.ios.youtube/19.45.4 (iPhone16,2; U; CPU iOS 18_1 like Mac OS X;)",
    "osName": "iPhone",
    "osVersion": "18.1.0.22B83",
    "hl": "en",
    "gl": "US",
}

# ✅ mweb client (أقل تقييداً من android)
MWEB_CLIENT = {
    "clientName": "MWEB",
    "clientVersion": "2.20241202.07.00",
    "userAgent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
    ),
    "hl": "en",
    "gl": "US",
}

INNERTUBE_API_URL = "https://www.youtube.com/youtubei/api/v1/player"
# ✅ API key محدّث
INNERTUBE_API_KEY = "AIzaSyB-63vPrdThhKuerbB2N_l7Kwwcxj6yUAc"


class YouTubeExtractor(BaseExtractor):

    def _extract_video_id(self, url: str) -> Optional[str]:
        m = YT_ID_PATTERN.search(url)
        return m.group(1) if m else None

    async def _innertube_request(self, video_id: str, client: dict = None) -> Optional[dict]:
        """Make an Innertube player API request."""
        if client is None:
            client = IOS_CLIENT

        payload = {
            "context": {"client": client},
            "videoId": video_id,
            "playbackContext": {
                "contentPlaybackContext": {
                    "html5Preference": "HTML5_PREF_WANTS",
                }
            },
            "contentCheckOk": True,
            "racyCheckOk": True,
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": client.get("userAgent", GENERIC_USER_AGENT),
            "X-YouTube-Client-Name": "5" if client["clientName"] == "IOS" else "2",
            "X-YouTube-Client-Version": client["clientVersion"],
            "Origin": "https://www.youtube.com",
            "Referer": "https://www.youtube.com/",
        }

        url = f"{INNERTUBE_API_URL}?key={INNERTUBE_API_KEY}&prettyPrint=false"

        return await self.fetch_json(
            url,
            headers=headers,
            method="POST",
            data=json.dumps(payload),
            timeout=15,
        )

    async def extract(self, url: str) -> Optional[VideoResult]:
        video_id = self._extract_video_id(url)
        if not video_id:
            return None

        # جرّب iOS أولاً ثم mweb
        data = None
        for client in [IOS_CLIENT, MWEB_CLIENT]:
            data = await self._innertube_request(video_id, client)
            if data:
                status = data.get("playabilityStatus", {}).get("status")
                if status == "OK":
                    break
                data = None

        if not data:
            return None

        playability = data.get("playabilityStatus", {})
        if playability.get("status") != "OK":
            reason = playability.get("reason", "unknown")
            self.logger.debug(f"YouTube not playable: {reason}")
            return None

        video_details = data.get("videoDetails", {})

        # تخطّى البث المباشر
        if video_details.get("isLive") or video_details.get("isLiveContent"):
            return None

        # تخطّى الفيديوهات الطويلة جداً (أكثر من ساعة)
        duration_seconds = int(video_details.get("lengthSeconds", 0))
        if duration_seconds > 3600:
            return None

        streaming_data = data.get("streamingData", {})
        combined  = streaming_data.get("formats", [])
        adaptive  = streaming_data.get("adaptiveFormats", [])
        title     = video_details.get("title", f"youtube_{video_id}")

        # الخيار 1: صيغة مدمجة (فيديو + صوت) بدون cipher
        for fmt in sorted(combined, key=lambda f: f.get("height", 0), reverse=True):
            if fmt.get("signatureCipher") or fmt.get("cipher"):
                continue
            if (fmt.get("mimeType", "").startswith("video/mp4")
                    and fmt.get("url")
                    and fmt.get("height", 0) <= 1080):
                return VideoResult(
                    url=fmt["url"],
                    filename=f"youtube_{video_id}.mp4",
                    title=title,
                    duration=duration_seconds,
                    thumbnail=f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
                )

        # الخيار 2: صيغة adaptive (فيديو منفصل) بدون cipher
        best_video = None
        best_audio = None

        for fmt in adaptive:
            if fmt.get("signatureCipher") or fmt.get("cipher"):
                continue
            mime = fmt.get("mimeType", "")
            if mime.startswith("video/mp4") and fmt.get("url") and fmt.get("height", 0) <= 1080:
                if not best_video or fmt.get("height", 0) > best_video.get("height", 0):
                    best_video = fmt
            elif mime.startswith("audio/") and fmt.get("url"):
                if not best_audio or fmt.get("bitrate", 0) > best_audio.get("bitrate", 0):
                    best_audio = fmt

        if best_video and best_video.get("url"):
            return VideoResult(
                url=best_video["url"],
                filename=f"youtube_{video_id}.mp4",
                audio_url=best_audio["url"] if best_audio else None,
                title=title,
                duration=duration_seconds,
                thumbnail=f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
            )

        # كل الصيغ محمية بـ cipher — يتولى yt-dlp التحميل
        self.logger.info(f"YouTube: cipher-protected, delegating to yt-dlp → {video_id}")
        return None
