"""
Instagram extractor — ported from Cobalt's instagram.js

Extraction chain (tries in order):
1. Mobile API via oembed → media_id → /api/v1/media/{id}/info/
2. Embed page parsing (/p/{id}/embed/captioned/)
3. GraphQL API (PolarisPostActionLoadPostQueryQuery)

All methods work without login for public posts.
"""

import re
import json
from typing import Optional
from urllib.parse import quote

from .base import BaseExtractor, VideoResult, GENERIC_USER_AGENT

MOBILE_HEADERS = {
    "x-ig-app-locale": "en_US",
    "x-ig-device-locale": "en_US",
    "x-ig-mapped-locale": "en_US",
    "user-agent": (
        "Instagram 275.0.0.27.98 Android (33/13; 280dpi; 720x1423; "
        "Xiaomi; Redmi 7; onclite; qcom; en_US; 458229237)"
    ),
    "accept-language": "en-US",
    "x-fb-http-engine": "Liger",
    "x-fb-client-ip": "True",
    "x-fb-server-cluster": "True",
    "content-length": "0",
}

COMMON_HEADERS = {
    "user-agent": GENERIC_USER_AGENT,
    "sec-gpc": "1",
    "sec-fetch-site": "same-origin",
    "x-ig-app-id": "936619743392459",
}

EMBED_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Dnt": "1",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": GENERIC_USER_AGENT,
}

# URL patterns
POST_PATTERN = re.compile(
    r'instagram\.com/(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)'
)
STORY_PATTERN = re.compile(
    r'instagram\.com/stories/([^/]+)/(\d+)'
)
SHARE_PATTERN = re.compile(
    r'instagram\.com/share/([A-Za-z0-9_-]+)'
)


class InstagramExtractor(BaseExtractor):

    def _extract_post_id(self, url: str) -> Optional[str]:
        m = POST_PATTERN.search(url)
        return m.group(1) if m else None

    def _extract_share_id(self, url: str) -> Optional[str]:
        m = SHARE_PATTERN.search(url)
        return m.group(1) if m else None

    # ------ Mobile API ------

    async def _get_media_id(self, post_id: str) -> Optional[str]:
        """Get numeric media_id from oembed endpoint."""
        oembed_url = f"https://i.instagram.com/api/v1/oembed/?url=https://www.instagram.com/p/{post_id}/"
        data = await self.fetch_json(oembed_url, headers=MOBILE_HEADERS)
        return data.get("media_id") if data else None

    async def _request_mobile_api(self, media_id: str) -> Optional[dict]:
        """Fetch media info from Instagram mobile API."""
        url = f"https://i.instagram.com/api/v1/media/{media_id}/info/"
        data = await self.fetch_json(url, headers=MOBILE_HEADERS)
        if data and data.get("items"):
            return data["items"][0]
        return None

    # ------ __a=1 API ------

    async def _request_a1_api(self, post_id: str) -> Optional[dict]:
        """Try Instagram's ?__a=1 JSON endpoint."""
        url = f"https://www.instagram.com/p/{post_id}/?__a=1&__d=dis"
        headers = {
            **EMBED_HEADERS,
            "x-ig-app-id": "936619743392459",
        }
        data = await self.fetch_json(url, headers=headers)
        if data:
            # Try to find the media item
            items = (
                data.get("items")
                or data.get("graphql", {}).get("shortcode_media")
                or None
            )
            if items:
                if isinstance(items, list) and items:
                    return items[0]
                return items
        return None

    # ------ Embed parsing ------

    async def _request_embed(self, post_id: str) -> Optional[dict]:
        """Parse the embed page for video/image URLs."""
        url = f"https://www.instagram.com/p/{post_id}/embed/captioned/"
        html = await self.fetch(url, headers=EMBED_HEADERS)
        if not html:
            # Try without captioned
            url = f"https://www.instagram.com/p/{post_id}/embed/"
            html = await self.fetch(url, headers=EMBED_HEADERS)
        if not html:
            return None

        # Method 1: extract video_url directly from HTML
        video_match = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
        if video_match:
            try:
                video_url = json.loads(f'"{video_match.group(1)}"')
                return {"video_url": video_url}
            except Exception:
                pass

        # Method 2: look for playable_url
        playable_match = re.search(r'"playable_url"\s*:\s*"([^"]+)"', html)
        if playable_match:
            try:
                video_url = json.loads(f'"{playable_match.group(1)}"')
                return {"video_url": video_url}
            except Exception:
                pass

        # Method 3: classic init data JSON
        try:
            for pattern in [
                r'"init",\[\],\[(.*?)\]\],',
                r'window\.__additionalDataLoaded\([^,]+,({.*?})\);',
                r'PolarisEmbedBootstrap\.handleInstance\([^,]+,\s*({.*?})\)',
            ]:
                match = re.search(pattern, html, re.DOTALL)
                if match:
                    embed_data = json.loads(match.group(1))
                    if isinstance(embed_data, dict) and embed_data.get("contextJSON"):
                        return json.loads(embed_data["contextJSON"])
                    if isinstance(embed_data, dict) and (
                        embed_data.get("video_url") or embed_data.get("display_url")
                    ):
                        return embed_data
        except Exception as e:
            self.logger.debug(f"Embed parse error: {e}")

        return None

    # ------ GraphQL API ------

    async def _request_gql(self, post_id: str) -> Optional[dict]:
        """Query Instagram's GraphQL API for post data."""
        try:
            # First fetch the post page to get tokens
            page_url = f"https://www.instagram.com/p/{post_id}/"
            html = await self.fetch(page_url, headers=EMBED_HEADERS)
            if not html:
                return None

            # Extract LSD token
            lsd_match = re.search(r'"LSD",\[\],({.*?}),\d+\]', html)
            lsd = "unknown"
            if lsd_match:
                try:
                    lsd = json.loads(lsd_match.group(1)).get("token", "unknown")
                except Exception:
                    pass

            # Extract CSRF
            csrf_match = re.search(r'"csrf_token":"([^"]+)"', html)
            csrf = csrf_match.group(1) if csrf_match else ""

            headers = {
                **EMBED_HEADERS,
                "x-ig-app-id": "936619743392459",
                "X-FB-LSD": lsd,
                "X-CSRFToken": csrf,
                "content-type": "application/x-www-form-urlencoded",
                "X-FB-Friendly-Name": "PolarisPostActionLoadPostQueryQuery",
            }

            body = {
                "__a": "1",
                "__d": "www",
                "lsd": lsd,
                "fb_api_caller_class": "RelayModern",
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
                headers=headers,
                method="POST",
                data=body,
            )
            if data and data.get("data"):
                return {"gql_data": data["data"]}
        except Exception as e:
            self.logger.debug(f"GQL error: {e}")
        return None

    # ------ Result extraction ------

    def _extract_from_mobile_api(self, data: dict, post_id: str) -> Optional[VideoResult]:
        """Extract video/photo from mobile API response (new format)."""
        from .base import MediaItem
        # Carousel / slideshow
        carousel = data.get("carousel_media")
        if carousel:
            items = []
            for idx, item in enumerate(carousel, 1):
                if item.get("video_versions"):
                    best = max(item["video_versions"], key=lambda v: v.get("width", 0) * v.get("height", 0))
                    items.append(MediaItem(url=best["url"], filename=f"instagram_{post_id}_{idx}.mp4", is_video=True))
                elif item.get("image_versions2", {}).get("candidates"):
                    img_url = item["image_versions2"]["candidates"][0]["url"]
                    items.append(MediaItem(url=img_url, filename=f"instagram_{post_id}_{idx}.jpg", is_video=False))
            if items:
                first = items[0]
                return VideoResult(
                    url=first.url,
                    filename=first.filename,
                    is_photo=not first.is_video,
                    carousel=items if len(items) > 1 else None,
                )
            return None

        # Single video
        if data.get("video_versions"):
            best = max(data["video_versions"], key=lambda v: v.get("width", 0) * v.get("height", 0))
            return VideoResult(
                url=best["url"],
                filename=f"instagram_{post_id}.mp4",
            )

        # Single image
        candidates = data.get("image_versions2", {}).get("candidates")
        if candidates:
            return VideoResult(
                url=candidates[0]["url"],
                filename=f"instagram_{post_id}.jpg",
                is_photo=True,
            )

        return None

    def _extract_from_gql(self, data: dict, post_id: str) -> Optional[VideoResult]:
        """Extract from GraphQL response (old format)."""
        shortcode_media = (
            data.get("gql_data", {}).get("shortcode_media")
            or data.get("gql_data", {}).get("xdt_shortcode_media")
        )
        if not shortcode_media:
            return None

        # Sidecar (carousel)
        sidecar = shortcode_media.get("edge_sidecar_to_children")
        if sidecar:
            for edge in sidecar.get("edges", []):
                node = edge.get("node", {})
                if node.get("is_video") and node.get("video_url"):
                    return VideoResult(
                        url=node["video_url"],
                        filename=f"instagram_{post_id}.mp4",
                    )
            # Fallback to first image
            for edge in sidecar.get("edges", []):
                node = edge.get("node", {})
                if node.get("display_url"):
                    return VideoResult(
                        url=node["display_url"],
                        filename=f"instagram_{post_id}.jpg",
                        is_photo=True,
                    )
            return None

        # Single video
        if shortcode_media.get("video_url"):
            return VideoResult(
                url=shortcode_media["video_url"],
                filename=f"instagram_{post_id}.mp4",
            )

        # Single image
        if shortcode_media.get("display_url"):
            return VideoResult(
                url=shortcode_media["display_url"],
                filename=f"instagram_{post_id}.jpg",
                is_photo=True,
            )

        return None

    def _extract_from_embed(self, data: dict, post_id: str) -> Optional[VideoResult]:
        """Extract from embed page data."""
        if not data:
            return None

        # Look for video_url in the context data
        video_url = data.get("video_url")
        if video_url:
            return VideoResult(
                url=video_url,
                filename=f"instagram_{post_id}.mp4",
            )

        # Look for display_url (image)
        display_url = data.get("display_url")
        if display_url:
            return VideoResult(
                url=display_url,
                filename=f"instagram_{post_id}.jpg",
                is_photo=True,
            )

        return None

    # ------ Main extract ------

    async def extract(self, url: str) -> Optional[VideoResult]:
        # Handle share links — resolve redirect first
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
            self.logger.debug(f"Could not extract post ID from {url}")
            return None

        # Strategy 1: Embed page (fastest, no auth needed)
        try:
            embed_data = await self._request_embed(post_id)
            if embed_data:
                result = self._extract_from_embed(embed_data, post_id)
                if result:
                    self.logger.info("Instagram: extracted via embed")
                    return result
        except Exception as e:
            self.logger.debug(f"Embed failed: {e}")

        # Strategy 2: __a=1 JSON API
        try:
            a1_data = await self._request_a1_api(post_id)
            if a1_data:
                result = self._extract_from_mobile_api(a1_data, post_id)
                if result:
                    self.logger.info("Instagram: extracted via __a=1 API")
                    return result
        except Exception as e:
            self.logger.debug(f"__a=1 API failed: {e}")

        # Strategy 3: Mobile API via oembed
        try:
            media_id = await self._get_media_id(post_id)
            if media_id:
                data = await self._request_mobile_api(media_id)
                if data:
                    result = self._extract_from_mobile_api(data, post_id)
                    if result:
                        self.logger.info("Instagram: extracted via mobile API")
                        return result
        except Exception as e:
            self.logger.debug(f"Mobile API failed: {e}")

        # Strategy 4: GraphQL
        try:
            gql_data = await self._request_gql(post_id)
            if gql_data:
                result = self._extract_from_gql(gql_data, post_id)
                if result:
                    self.logger.info("Instagram: extracted via GQL")
                    return result
        except Exception as e:
            self.logger.debug(f"GQL failed: {e}")

        # Strategy 5: try /p/{post_id}/?__a=1 with different session headers
        try:
            for cookie_hint in ["", "ig_did=1; ig_nrcb=1;"]:
                headers = {
                    **MOBILE_HEADERS,
                    "cookie": cookie_hint,
                    "referer": "https://www.instagram.com/",
                }
                data = await self.fetch_json(
                    f"https://www.instagram.com/p/{post_id}/?__a=1&__d=dis",
                    headers=headers,
                )
                if data:
                    items = data.get("items") or [data.get("graphql", {}).get("shortcode_media")]
                    items = [i for i in items if i]
                    if items:
                        result = self._extract_from_mobile_api(items[0], post_id)
                        if result:
                            self.logger.info("Instagram: extracted via mobile session")
                            return result
        except Exception as e:
            self.logger.debug(f"Mobile session failed: {e}")

        self.logger.warning(f"Instagram: all methods failed for {post_id}")
        return None
