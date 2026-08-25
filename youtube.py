import asyncio
import re
from typing import Any, Dict, List
import yt_dlp

from app.core.config import settings
from app.core.exceptions import ContentUnavailableError, InvalidURLError, PrivateContentError
from app.core.logging import logger
from app.platforms.base import BasePlatformAdapter, MediaMetadata, MediaQuality
from app.security.sanitizer import sanitize_url_parameters


class YouTubeAdapter(BasePlatformAdapter):
    URL_PATTERNS = [
        re.compile(r"(https?://)?(www\.|m\.)?youtube\.com/watch\?v=[\w-]+"),
        re.compile(r"(https?://)?youtu\.be/[\w-]+"),
        re.compile(r"(https?://)?(www\.|m\.)?youtube\.com/shorts/[\w-]+"),
        re.compile(r"(https?://)?(www\.|m\.)?youtube\.com/v/[\w-]+"),
    ]

    @property
    def platform_name(self) -> str:
        return "youtube"

    def can_handle(self, url: str) -> bool:
        return any(pattern.search(url) for pattern in self.URL_PATTERNS)

    def normalize_url(self, url: str) -> str:
        clean_url = sanitize_url_parameters(url)
        # Normalize shorts URL to watch URL standard
        shorts_match = re.search(r"youtube\.com/shorts/([\w-]+)", clean_url)
        if shorts_match:
            video_id = shorts_match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"

        youtu_be_match = re.search(r"youtu\.be/([\w-]+)", clean_url)
        if youtu_be_match:
            video_id = youtu_be_match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"

        return clean_url

    async def extract_info(self, url: str) -> MediaMetadata:
        normalized_url = self.normalize_url(url)

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "skip_download": True,
            "socket_timeout": 30,
            "extractor_args": {"youtube": {"player_client": ["android_vr", "web_safari"]}},
        }

        loop = asyncio.get_event_loop()
        try:
            info = await loop.run_in_executor(
                None, lambda: self._extract_yt_dlp(normalized_url, ydl_opts)
            )
        except Exception as e:
            err_str = str(e).lower()
            # ONLY trigger PrivateContentError on genuine markers, NOT generic "sign in" messages
            if any(marker in err_str for marker in ("this video is private", "video is private", "private video", "only available to members")):
                raise PrivateContentError("This YouTube video is genuinely private or restricted to members.")
            elif "not available" not in err_str or "deleted" in err_str:
                raise ContentUnavailableError("YouTube video not available or deleted.")
            else:
                logger.error(f"YouTube metadata extraction error: {e}")
                raise ContentUnavailableError(f"Failed to analyze YouTube video: {str(e)}")

        qualities = self._parse_qualities(info.get("formats", []))

        return MediaMetadata(
            platform=self.platform_name,
            url=url,
            normalized_url=normalized_url,
            title=info.get("title", "YouTube Video"),
            uploader=info.get("uploader") or info.get("channel", "YouTube"),
            duration=info.get("duration", 0),
            thumbnail=info.get("thumbnail"),
            qualities=qualities,
            raw_info=info,
        )

    def _extract_yt_dlp(self, url: str, opts: dict) -> dict:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _parse_qualities(self, formats: List[Dict[str, Any]]) -> List[MediaQuality]:
        qualities: List[MediaQuality] = []
        seen_heights = set()

        # Target resolutions in descending order
        target_resolutions = [1080, 720, 480, 360]

        # 1. Best overall option
        qualities.append(
            MediaQuality(
                format_id="best",
                label="🎬 Best Quality",
                ext="mp4",
                has_video=True,
                has_audio=True,
            )
        )

        # 2. Filter specific video formats
        for fmt in formats:
            height = fmt.get("height")
            vcodec = fmt.get("vcodec", "none")
            if height and height in target_resolutions and vcodec != "none":
                if height not in seen_heights:
                    seen_heights.add(height)
                    qualities.append(
                        MediaQuality(
                            format_id=f"bestvideo[height<={height}]+bestaudio/best[height<={height}]",
                            label=f"📹 {height}p",
                            ext="mp4",
                            resolution=f"{height}p",
                            filesize_approx=fmt.get("filesize") or fmt.get("filesize_approx"),
                            has_video=True,
                            has_audio=True,
                        )
                    )

        # 3. Audio extraction option
        qualities.append(
            MediaQuality(
                format_id="bestaudio/best",
                label="🎵 Audio Only (MP3)",
                ext="mp3",
                has_video=False,
                has_audio=True,
            )
        )

        return qualities
