from dataclasses import replace

from linguacaption.config import Settings
from linguacaption.core.presentation import CaptionPresenter
from linguacaption.domain import Caption


def caption(utterance, revision=1, *, final=True, translation="译文"):
    return Caption(utterance, revision, f"sentence {utterance}.{revision}", "en", final, 0, 10, translation)


def test_each_complete_pair_has_four_seconds_to_read():
    reader = CaptionPresenter(Settings())
    first, second = caption(1), caption(2)
    assert reader.push(first, 0) == first
    assert reader.push(second, 1) is None
    assert reader.advance(3.99) is None
    assert reader.current == first
    assert reader.advance(4) == second
    assert not reader.expired(15.99)
    assert reader.expired(16)


def test_translation_arrival_gets_its_own_reading_time():
    reader = CaptionPresenter(Settings())
    original = caption(1, translation="", final=False)
    translated = replace(original, translation="完整译文", final=True)
    reader.push(original, 0)
    assert reader.push(translated, 2) == translated
    assert reader.push(caption(2), 3) is None
    assert reader.advance(5.99) is None
    assert reader.advance(6).utterance == 2


def test_partial_revision_keeps_previous_matched_translation_visible():
    reader = CaptionPresenter(Settings())
    first = caption(1, final=False)
    reader.push(first, 0)
    revision = caption(1, 2, final=False, translation="")
    assert reader.push(revision, 1.2) is None
    assert reader.current == first
    assert reader.advance(2) is None
    translated = replace(revision, translation="新的完整译文")
    assert reader.push(translated, 2.1) == translated
    assert reader.current.original == revision.original


def test_original_updates_coalesce_and_stale_translation_is_rejected():
    reader = CaptionPresenter(Settings(mode="original"))
    reader.push(caption(1, final=False, translation=""), 0)
    latest = caption(1, 3, final=False, translation="")
    assert reader.push(caption(1, 2, final=False, translation=""), .2) is None
    assert reader.push(latest, .4) is None
    assert reader.advance(1) == latest
    assert reader.push(caption(1, 2), 1.1) is None
    assert reader.current == latest


def test_translation_mode_waits_for_text_and_failed_translation_does_not_block_next():
    reader = CaptionPresenter(Settings(mode="translation"))
    assert reader.push(caption(1, translation=""), 0) is None
    next_caption = caption(2)
    assert reader.push(next_caption, 1) == next_caption
    assert reader.current == next_caption


def test_queue_is_bounded_and_reset_removes_pending_old_session():
    reader = CaptionPresenter(Settings())
    reader.push(caption(1), 0)
    for utterance in range(2, 20):
        reader.push(caption(utterance), .1)
    assert len(reader._pending) == 3
    assert reader.advance(4).utterance == 17
    reader.reset()
    assert reader.advance(100) is None
    assert not reader.expired(100)
