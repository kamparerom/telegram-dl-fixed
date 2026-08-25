import asyncio
import os
from typing import Callable, Optional
import httpx
import yt_dlp

from app.core.config import settings
from app.core.exceptions import DownloadFailedError, DownloadTimeoutError
from app.core.logging import logger
from app.security.sanitizer import sanitize_filename


class MediaDownloader:
    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        os.makedirs(self.download_dir, exist_ok=True)

    async def download_media(
        self,
        url: str,
        format_id: str = "best",
        progress_callback: Optional[Callable[[dict], None]] = None,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> str:
        # 1. Direct stream for resolved HTTP/CDN URLs or Threads/TikTok fallback links
        if (
            url
            and (url.startswith("http://") or url.startswith("https://"))
            and ("cdninstagram.com" in url or "fbcdn.net" in url or ".mp4" in url or "tikwm.com" in url or "tiklydown" in url)
        ) or (format_id and (format_id.startswith("http://") or format_id.startswith("https://"))):
            direct_target = url if (url and url.startswith("http")) else format_id
            logger.info(f"MediaDownloader: Direct HTTP stream download for {direct_target[:80]}...")
            return await self.download_direct_url(direct_target, cancel_event=cancel_event)

        # 2. For yt-dlp, if format_id is a custom label (e.g. direct_link_0, threads_direct), reset format selector to "best"
        ydl_format = format_id if format_id and not format_id.startswith("direct_link_") and format_id != "threads_direct" else "best"

        out_template = os.path.join(self.download_dir, "%(title).30s_%(id).30s.%(ext)s")

        def yt_dlp_hook(d):
            if cancel_event and cancel_event.is_set():
                raise Exception("Download cancelled by user.")

            if d["status"] == "downloading" and progress_callback:
                downloaded = d.get("downloaded_bytes", 0)
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                percent = (downloaded / total * 100) if total > 0 else 0

                progress_data = {
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": speed,
                    "eta": eta,
                    "percent": percent,
                }
                progress_callback(progress_data)

        ydl_opts = {
            "format": ydl_format,
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [yt_dlp_hook],
            "socket_timeout": 30,
            "extractor_args": {"youtube": {"player_client": ["tv", "web"]}},
        }

        loop = asyncio.get_event_loop()
        try:
            downloaded_file = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: self._run_download(url, ydl_opts)),
                timeout=settings.DOWNLOAD_TIMEOUT,
            )
            if not downloaded_file or not os.path.exists(downloaded_file):
                raise DownloadFailedError("Downloaded file could not be found on disk.")
            return downloaded_file

        except asyncio.TimeoutError:
            raise DownloadTimeoutError(settings.DOWNLOAD_TIMEOUT)
        except Exception as e:
            if "cancelled" in str(e).lower():
                raise
            logger.error(f"MediaDownloader error: {e}")
            raise DownloadFailedError(f"Download failed: {str(e)}")

    async def download_direct_url(
        self,
        media_url: str,
        filename: str = "media_download.mp4",
        cancel_event: Optional[asyncio.Event] = None,
    ) -> str:
        """Downloads direct video/audio stream URL via HTTP stream."""
        dest_path = os.path.join(self.download_dir, sanitize_filename(filename))
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "Accept": "*/*",
        }

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
                async with client.stream("GET", media_url, headers=headers) as resp:
                    if resp.status_code not in (200, 206):
                        raise DownloadFailedError(f"HTTP stream request failed with status code {resp.status_code}")

                    with open(dest_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            if cancel_event and cancel_event.is_set():
                                raise Exception("Download cancelled by user.")
                            f.write(chunk)

            if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
                raise DownloadFailedError("Direct stream downloaded 0 bytes.")

            return dest_path
        except Exception as e:
            logger.error(f"Direct URL stream error: {e}")
            raise DownloadFailedError(f"Failed to stream media: {str(e)}")

    def _run_download(self, url: str, opts: dict) -> str:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # If merged format changed extension
            if not os.path.exists(filename):
                base, _ = os.path.splitext(filename)
                for ext in ["mp4", "mkv", "webm", "m4a", "mp3"]:
                    candidate = f"{base}.{ext}"
                    if os.path.exists(candidate):
                        return candidate
            return filename
