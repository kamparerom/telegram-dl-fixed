import re
from app.core.exceptions import UnsupportedPlatformError
from app.platforms.base import BasePlatformAdapter, MediaMetadata


class SnapchatAdapter(BasePlatformAdapter):
    URL_PATTERNS = [
        re.compile(r"(https?://)?(www\.|t\.|story\.)?snapchat\.com/"),
    ]

    @property
    def platform_name(self) -> str:
        return "snapchat"

    def can_handle(self, url: str) -> bool:
        return any(pattern.search(url) for pattern in self.URL_PATTERNS)

    def normalize_url(self, url: str) -> str:
        from app.security.sanitizer import sanitize_url_parameters
        return sanitize_url_parameters(url)

    async def extract_info(self, url: str) -> MediaMetadata:
        err = UnsupportedPlatformError("Snapchat")
        err.user_message = "Snapchat is not supported by this bot. Try YouTube, TikTok, Instagram, X, Threads, or Facebook."
        raise err
