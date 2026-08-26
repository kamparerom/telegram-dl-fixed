import asyncio
import re
from typing import Any, Dict, List, Optional
import httpx
import yt_dlp

from app.core.exceptions import ContentUnavailableError
from app.core.logging import logger
from app.platforms.base import BasePlatformAdapter, MediaMetadata, MediaQuality
from app.security.sanitizer import sanitize_url_parameters


class TikTokAdapter(BasePlatformAdapter):
    URL_PATTERNS = [
        re.compile(r"(https?://)?(www\.|vm\.|vt\.|m\.|t\.)?tiktok\.com/"),
    ]

    @property
    def platform_name(self) -> str:
        return "tiktok"

    def can_handle(self, url: str) -> bool:
        return any(pattern.search(url) for pattern in self.URL_PATTERNS)

    def normalize_url(self, url: str) -> str:
        return sanitize_url_parameters(url)

    async def extract_info(self, url: str) -> MediaMetadata:
        normalized_url = self.normalize_url(url)

        # 0. Resolve short links (vt.tiktok.com / vm.tiktok.com / t.tiktok.com)
        if any(domain in normalized_url for domain in ["vt.tiktok.com", "vm.tiktok.com", "t.tiktok.com"]):
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                    res = await client.get(normalized_url, headers=headers)
                    redirected = str(res.url)
                    if "tiktok.com" in redirected:
                        normalized_url = redirected
            except Exception as e:
                logger.warning(f"Failed to un-shorten TikTok URL {normalized_url}: {e}")

        # 1. Try primary yt-dlp extraction
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "socket_timeout": 30,
            }
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None, lambda: self._extract_yt_dlp(normalized_url, ydl_opts)
            )

            qualities = [
                MediaQuality(
                    format_id="best",
                    label="🎬 HD Video (No Watermark)",
                    ext="mp4",
                    has_video=True,
                    has_audio=True,
                ),
                MediaQuality(
                    format_id="bestaudio/best",
                    label="🎵 Audio Only (MP3)",
                    ext="mp3",
                    has_video=False,
                    has_audio=True,
                ),
            ]

            return MediaMetadata(
                platform=self.platform_name,
                url=url,
                normalized_url=normalized_url,
                title=info.get("title") or info.get("description") or "TikTok Video",
                uploader=info.get("uploader") or info.get("creator") or "TikTok Creator",
                duration=info.get("duration", 0),
                thumbnail=info.get("thumbnail"),
                qualities=qualities,
                raw_info=info,
            )
        except Exception as e:
            logger.warning(f"yt-dlp failed for TikTok ({e}).")
            
            # yt-dlp is the only extractor
            logger.warning("TikTok yt-dlp extraction failed; no external fallback used.")

        raise ContentUnavailableError("Failed to extract TikTok video. The video may be private, region-locked, or deleted.")

    def _extract_yt_dlp(self, url: str, opts: dict) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
