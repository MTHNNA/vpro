"""
Instagram extractor — ported from Cobalt's instagram.js

✅ Updated: Mobile User-Agent to Instagram 341 (2025)
✅ Updated: Added x-asbd-id and other required headers
✅ Updated: Better carousel extraction
✅ Updated: Improved embed parsing patterns

Extraction chain (tries in order):
1. Embed page parsing (/p/{id}/embed/captioned/)
2. __a=1 JSON API
3. Mobile API via oembed → media_id → /api/v1/media/{id}/info/
4. GraphQL API (PolarisPostActionLoadPostQueryQuery)
5. Mobile session fallback
"""

import re
import json
from typing import Optional
from urllib.parse import quote

from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

# ✅ Mobile headers محدّثة (Instagram 341 — 2025)
MOBILE_HEADERS = {
    "x-ig-app-locale"    : "en_US",
    "x-ig-device-locale" : "en_US",
    "x-ig-mapped-locale" : "en_US",
    "x-ig-app-id"        : "636761069773390",
    "x-asbd-id"          : "129477",
    "x-ig-bandwidth-speed-kbps": "5000",
    "user-agent": (
        "Instagram 341.0.0.36.98 Android (33/13; 420dpi; 1080x2280; "
        "samsung; SM-G991B; o1s; exynos2100; en_US; 561634148)"
    ),
    "accept-language": "en-US,en;q=0.9",
    "x-fb-http-engine" : "Liger",
    "x-fb-client-ip"   : "True",
    "x-fb-server-cluster": "True",
    "content-length"   : "0",
    "connection"       : "keep-alive",
}

# ✅ iPhone headers محدّثة
IPHONE_HEADERS = {
    "x-ig-app-locale"    : "en_US",
    "x-ig-device-locale" : "en_US",
    "x-ig-app-id"        : "636761069773390",
    "user-agent": (
        "Instagram 341.0.0.36.98 (iPhone16,2; iOS 18_1; en_US; en; "
        "scale=3.00; 1290x2796; 561634148) AppleWebKit/420+"
    ),
    "accept-language" : "en-US,en;q=0.9",
    "x-fb-http-engine": "Liger",
    "connection"      : "keep-alive",
}

EMBED_HEADERS = {
    "Accept"         : "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control"  : "max-age=0",
    "Dnt"            : "1",
    "Sec-Ch-Ua"      : '"Chromium";v="130", "Google Chrome";v="130"',
    "Sec-Ch-Ua-Mobile"  : "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest" : "document",
    "Sec-Fetch-Mode" : "navigate",
    "Sec-Fetch-Site" : "none",
    "Sec-Fetch-User" : "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent"     : (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
}

POST_PATTERN = re.compile(
    r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)'
)
STORY_PATTERN  = re.compile(r'instagram\.com/stories/([^/]+)/(\d+)')
SHARE_PATTERN  = re.compile(r'instagram\.com/share/([A-Za-z0-9_-]+)')


class InstagramExtractor(BaseExtractor):

    def _extract_post_id(self, url: str) -> Optional[str]:
        m = POST_PATTERN.search(url)
        return m.group(1) if m else None

    def _extract_share_id(self, url: str) -> Optional[str]:
        m = SHARE_PATTERN.search(url)
        return m.group(1) if m else None

    # ── Mobile API ──────────────────────────────────────────────────────────

    async def _get_media_id(self, post_id: str) -> Optional[str]:
        """Get numeric media_id from oembed."""
        url  = f"https://i.instagram.com/api/v1/oembed/?url=https://www.instagram.com/p/{post_id}/"
        data = await self.fetch_json(url, headers=MOBILE_HEADERS)
        return data.get("media_id") if data else None

    async def _request_mobile_api(self, media_id: str) -> Optional[dict]:
        """Fetch media info from Instagram mobile API."""
        url  = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        # جرّب Android ثم iPhone
        for headers in [MOBILE_HEADERS, IPHONE_HEADERS]:
            data = await self.fetch_json(url, headers=headers)
            if data and data.get("items"):
                return data["items"][0]
        return None

    # ── __a=1 API ───────────────────────────────────────────────────────────

    async def _request_a1_api(self, post_id: str) -> Optional[dict]:
        url     = f"https://www.instagram.com/p/{post_id}/?__a=1&__d=dis"
        headers = {**EMBED_HEADERS, "x-ig-app-id": "936619743392459"}
        data    = await self.fetch_json(url, headers=headers)
        if data:
            items = (
                data.get("items")
                or [data.get("graphql", {}).get("shortcode_media")]
            )
            items = [i for i in items if i]
            if items:
                return items[0]
        return None

    # ── Embed parsing ───────────────────────────────────────────────────────

    async def _request_embed(self, post_id: str) -> Optional[dict]:
        for path in [f"/p/{post_id}/embed/captioned/", f"/p/{post_id}/embed/"]:
            html = await self.fetch(f"https://www.instagram.com{path}", headers=EMBED_HEADERS)
            if not html:
                continue

            # video_url مباشرة في HTML
            for pattern in [r'"video_url"\s*:\s*"([^"]+)"', r'"playable_url"\s*:\s*"([^"]+)"']:
                m = re.search(pattern, html)
                if m:
                    try:
                        return {"video_url": json.loads(f'"{m.group(1)}"')}
                    except Exception:
                        pass

            # display_url (صورة)
            m = re.search(r'"display_url"\s*:\s*"([^"]+)"', html)
            if m:
                try:
                    return {"display_url": json.loads(f'"{m.group(1)}"')}
                except Exception:
                    pass

            # JSON init data
            for pattern in [
                r'"init",\[\],\[(.*?)\]\],',
                r'window\.__additionalDataLoaded\([^,]+,({.*?})\);',
                r'PolarisEmbedBootstrap\.handleInstance\([^,]+,\s*({.*?})\)',
            ]:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    try:
                        embed_data = json.loads(match.group(1))
                        if isinstance(embed_data, dict) and (
                            embed_data.get("video_url") or embed_data.get("display_url")
                        ):
                            return embed_data
                        if isinstance(embed_data, dict) and embed_data.get("contextJSON"):
                            return json.loads(embed_data["contextJSON"])
                    except Exception:
                        pass

        return None

    # ── GraphQL ─────────────────────────────────────────────────────────────

    async def _request_gql(self, post_id: str) -> Optional[dict]:
        try:
            html = await self.fetch(
                f"https://www.instagram.com/p/{post_id}/",
                headers=EMBED_HEADERS,
            )
            if not html:
                return None

            lsd = "unknown"
            m = re.search(r'"LSD",\[\],({.*?}),\d+\]', html)
            if m:
                try:
                    lsd = json.loads(m.group(1)).get("token", "unknown")
                except Exception:
                    pass

            csrf = ""
            m = re.search(r'"csrf_token":"([^"]+)"', html)
            if m:
                csrf = m.group(1)

            headers = {
                **EMBED_HEADERS,
                "x-ig-app-id"          : "936619743392459",
                "X-FB-LSD"             : lsd,
                "X-CSRFToken"          : csrf,
                "content-type"         : "application/x-www-form-urlencoded",
                "X-FB-Friendly-Name"   : "PolarisPostActionLoadPostQueryQuery",
            }

            body = {
                "__a": "1", "__d": "www", "lsd": lsd,
                "fb_api_caller_class"  : "RelayModern",
                "fb_api_req_friendly_name": "PolarisPostActionLoadPostQueryQuery",
                "variables": json.dumps({
                    "shortcode": post_id,
                    "fetch_tagged_user_count": None,
                    "hoisted_comment_id": None,
                    "hoisted_reply_id": None,
                }),
                "server_timestamps": "true",
                "doc_id": "8845758582119845",
            }

            data = await self.fetch_json(
                "https://www.instagram.com/graphql/query",
                headers=headers, method="POST", data=body,
            )
            if data and data.get("data"):
                return {"gql_data": data["data"]}
        except Exception as e:
            self.logger.debug(f"GQL error: {e}")
        return None

    # ── Result extraction ────────────────────────────────────────────────────

    def _extract_from_mobile_api(self, data: dict, post_id: str) -> Optional[VideoResult]:
        from .base import MediaItem

        carousel = data.get("carousel_media")
        if carousel:
            items = []
            for idx, item in enumerate(carousel, 1):
                if item.get("video_versions"):
                    best = max(item["video_versions"],
                               key=lambda v: v.get("width", 0) * v.get("height", 0))
                    items.append(MediaItem(
                        url=best["url"],
                        filename=f"instagram_{post_id}_{idx}.mp4",
                        is_video=True,
                    ))
                elif item.get("image_versions2", {}).get("candidates"):
                    img = item["image_versions2"]["candidates"][0]["url"]
                    items.append(MediaItem(
                        url=img,
                        filename=f"instagram_{post_id}_{idx}.jpg",
                        is_video=False,
                    ))
            if items:
                first = items[0]
                return VideoResult(
                    url=first.url,
                    filename=first.filename,
                    is_photo=not first.is_video,
                    carousel=items if len(items) > 1 else None,
                )

        if data.get("video_versions"):
            best = max(data["video_versions"],
                       key=lambda v: v.get("width", 0) * v.get("height", 0))
            return VideoResult(url=best["url"], filename=f"instagram_{post_id}.mp4")

        candidates = data.get("image_versions2", {}).get("candidates")
        if candidates:
            return VideoResult(
                url=candidates[0]["url"],
                filename=f"instagram_{post_id}.jpg",
                is_photo=True,
            )
        return None

    def _extract_from_gql(self, data: dict, post_id: str) -> Optional[VideoResult]:
        shortcode_media = (
            data.get("gql_data", {}).get("shortcode_media")
            or data.get("gql_data", {}).get("xdt_shortcode_media")
        )
        if not shortcode_media:
            return None

        sidecar = shortcode_media.get("edge_sidecar_to_children")
        if sidecar:
            for edge in sidecar.get("edges", []):
                node = edge.get("node", {})
                if node.get("is_video") and node.get("video_url"):
                    return VideoResult(url=node["video_url"],
                                       filename=f"instagram_{post_id}.mp4")
            for edge in sidecar.get("edges", []):
                node = edge.get("node", {})
                if node.get("display_url"):
                    return VideoResult(url=node["display_url"],
                                       filename=f"instagram_{post_id}.jpg",
                                       is_photo=True)

        if shortcode_media.get("video_url"):
            return VideoResult(url=shortcode_media["video_url"],
                               filename=f"instagram_{post_id}.mp4")
        if shortcode_media.get("display_url"):
            return VideoResult(url=shortcode_media["display_url"],
                               filename=f"instagram_{post_id}.jpg",
                               is_photo=True)
        return None

    def _extract_from_embed(self, data: dict, post_id: str) -> Optional[VideoResult]:
        if not data:
            return None
        if data.get("video_url"):
            return VideoResult(url=data["video_url"],
                               filename=f"instagram_{post_id}.mp4")
        if data.get("display_url"):
            return VideoResult(url=data["display_url"],
                               filename=f"instagram_{post_id}.jpg",
                               is_photo=True)
        return None

    # ── Main extract ─────────────────────────────────────────────────────────

    async def extract(self, url: str) -> Optional[VideoResult]:
        # حل روابط المشاركة المختصرة
        share_id = self._extract_share_id(url)
        if share_id:
            resolved = await self.resolve_redirect(
                f"https://www.instagram.com/share/{share_id}/",
                headers={"User-Agent": "curl/7.88.1"},
            )
            if resolved:
                url = resolved

        post_id = self._extract_post_id(url)
        if not post_id:
            return None

        # 1️⃣ Embed page
        try:
            embed_data = await self._request_embed(post_id)
            if embed_data:
                result = self._extract_from_embed(embed_data, post_id)
                if result:
                    self.logger.info("Instagram ✅ via embed")
                    return result
        except Exception as e:
            self.logger.debug(f"Embed failed: {e}")

        # 2️⃣ __a=1 API
        try:
            a1_data = await self._request_a1_api(post_id)
            if a1_data:
                result = self._extract_from_mobile_api(a1_data, post_id)
                if result:
                    self.logger.info("Instagram ✅ via __a=1")
                    return result
        except Exception as e:
            self.logger.debug(f"__a=1 failed: {e}")

        # 3️⃣ Mobile API
        try:
            media_id = await self._get_media_id(post_id)
            if media_id:
                data = await self._request_mobile_api(media_id)
                if data:
                    result = self._extract_from_mobile_api(data, post_id)
                    if result:
                        self.logger.info("Instagram ✅ via mobile API")
                        return result
        except Exception as e:
            self.logger.debug(f"Mobile API failed: {e}")

        # 4️⃣ GraphQL
        try:
            gql_data = await self._request_gql(post_id)
            if gql_data:
                result = self._extract_from_gql(gql_data, post_id)
                if result:
                    self.logger.info("Instagram ✅ via GQL")
                    return result
        except Exception as e:
            self.logger.debug(f"GQL failed: {e}")

        # 5️⃣ Fallback: mobile session بـ cookie بسيط
        try:
            for hdrs in [MOBILE_HEADERS, IPHONE_HEADERS]:
                data = await self.fetch_json(
                    f"https://www.instagram.com/p/{post_id}/?__a=1&__d=dis",
                    headers={**hdrs, "referer": "https://www.instagram.com/"},
                )
                if data:
                    items = data.get("items") or [data.get("graphql", {}).get("shortcode_media")]
                    items = [i for i in items if i]
                    if items:
                        result = self._extract_from_mobile_api(items[0], post_id)
                        if result:
                            self.logger.info("Instagram ✅ via mobile session fallback")
                            return result
        except Exception as e:
            self.logger.debug(f"Mobile session failed: {e}")

        self.logger.warning(f"Instagram: all methods failed for {post_id}")
        return None
