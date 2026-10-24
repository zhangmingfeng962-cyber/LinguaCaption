"""Current speech takes priority; retention only applies during silence."""
from ..config import Settings
from ..domain import Caption


class CaptionPresenter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        self.current: Caption | None = None
        self._latest: Caption | None = None
        self._activity_at = 0.0

    def push(self, caption: Caption, now: float) -> Caption | None:
        previous = self._latest
        if previous and (caption.key < previous.key or (
                caption.key == previous.key and previous.translation and not caption.translation)):
            return None
        self._latest = caption
        if previous and caption == previous:
            return None
        # Clear obsolete translations immediately, including translation-only mode.
        self._activity_at = now
        self.current = caption
        return caption

    def advance(self, now: float) -> Caption | None:
        return None

    def expired(self, now: float) -> bool:
        return bool(self.current and (now - self._activity_at) * 1000 >= self.settings.subtitle_timeout_ms)
