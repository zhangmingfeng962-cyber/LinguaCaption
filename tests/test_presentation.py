from dataclasses import replace

from linguacaption.config import Settings
from linguacaption.core.presentation import CaptionPresenter
from linguacaption.domain import Caption


def caption(utterance, revision=1, *, final=True, translation="译文"):
    return Caption(utterance, revision, f"sentence {utterance}.{revision}", "en", final, 0, 10, translation)


def test_new_speech_never_waits_for_previous_reading_time():
    reader = CaptionPresenter(Settings(subtitle_timeout_ms=12000))
    for i in range(1, 100):
        incoming = caption(i)
        assert reader.push(incoming, i / 10) == incoming
    assert reader.current.utterance == 99
    assert reader.advance(100) is None


def test_partial_revision_updates_immediately_and_invalidates_translation():
    reader = CaptionPresenter(Settings(mode="bilingual"))
    reader.push(caption(1, final=False), 0)
    revision = caption(1, 2, final=False, translation="")
    assert reader.push(revision, .2) == revision
    assert reader.current.translation == ""
    assert reader.push(caption(1, 1), .3) is None
    translated = replace(revision, translation="匹配当前原文")
    assert reader.push(translated, .4) == translated
    assert reader.push(revision, .5) is None


def test_translation_only_clears_old_text_while_new_translation_is_pending():
    reader = CaptionPresenter(Settings(mode="translation"))
    reader.push(caption(1), 0)
    new = caption(2, translation="")
    assert reader.push(new, .1) == new
    assert reader.current.translation == ""
    assert reader.push(caption(1), .2) is None
    assert reader.push(caption(3), .3).utterance == 3


def test_retention_counts_from_last_changed_content_not_duplicates_or_stale_events():
    reader = CaptionPresenter(Settings())
    first = caption(1)
    reader.push(first, 10)
    assert reader.push(first, 12) is None
    assert reader.push(caption(0), 13) is None
    assert not reader.expired(13.99)
    assert reader.expired(14)
    reader.reset()
    assert reader.current is None and not reader.expired(100)
    assert reader.advance(100) is None
