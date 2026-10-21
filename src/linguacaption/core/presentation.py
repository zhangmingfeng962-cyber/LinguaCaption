"""Bounded reading buffer, separate from recognition and translation throughput."""
from collections import OrderedDict

from ..config import Settings
from ..domain import Caption


class CaptionPresenter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.reset()

    def reset(self) -> None:
        self.current: Caption | None = None
        self._revision: Caption | None = None
        self._pending: OrderedDict[int, Caption] = OrderedDict()
        self._shown_at = self._activity_at = 0.0

    def push(self, caption: Caption, now: float) -> Caption | None:
        if self.current and caption.key < self.current.key:
            return None
        self._activity_at = now
        if self.current and caption.utterance == self.current.utterance:
            old = self._revision or self.current
            if caption.key < old.key or (caption.key == old.key and old.translation and not caption.translation):
                return None
            self._revision = caption
        else:
            old = self._pending.get(caption.utterance)
            if old and (caption.key < old.key or (caption.key == old.key and old.translation and not caption.translation)):
                return None
            self._pending[caption.utterance] = caption
            self._pending = OrderedDict(sorted(self._pending.items()))
            # Bound added viewing lag during continuous fast speech.
            while len(self._pending) > 3:
                self._pending.popitem(last=False)
        return self.advance(now)

    def _ready(self, caption: Caption) -> bool:
        if self.settings.mode == "original" or caption.translation:
            return True
        if self.settings.mode == "translation":
            return False
        # Once bilingual text is visible, keep the complete pair while waiting
        # for a matching revision, rather than blanking the translation.
        return not self.current or not self.current.translation

    def _commit(self, caption: Caption, now: float) -> Caption | None:
        previous = self.current
        self.current = caption
        if previous and (previous.original, previous.translation, previous.final, previous.utterance) == (
                caption.original, caption.translation, caption.final, caption.utterance):
            return None
        self._shown_at = now
        return caption

    def advance(self, now: float) -> Caption | None:
        revision = self._revision
        if revision and self._ready(revision):
            translated = bool(revision.translation and self.current and not self.current.translation)
            if revision.final or translated or now - self._shown_at >= 1.0:
                self._revision = None
                shown = self._commit(revision, now)
                if shown:
                    return shown
        if self.current and (now - self._shown_at) * 1000 < self.settings.subtitle_hold_ms:
            return None
        candidate = next((caption for caption in self._pending.values() if self._ready(caption)), None)
        if candidate:
            for utterance in list(self._pending):
                if utterance <= candidate.utterance:
                    del self._pending[utterance]
            self._revision = None
            return self._commit(candidate, now)
        return None

    def expired(self, now: float) -> bool:
        timeout = max(self.settings.subtitle_timeout_ms, self.settings.subtitle_hold_ms)
        return self.current is not None and (now - max(self._activity_at, self._shown_at)) * 1000 >= timeout
