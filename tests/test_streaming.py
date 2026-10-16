import threading
from dataclasses import dataclass

import numpy as np

from linguacaption.audio import AudioResampler
from linguacaption.config import Settings
from linguacaption.core.mailbox import LatestMailbox
from linguacaption.core.segmenter import Segmenter
from linguacaption.domain import AudioChunk


def feed_frames(segmenter, speech_ms, silence_ms, offset=0):
    pcm = np.concatenate((np.full(speech_ms * 16, .1, np.float32), np.zeros(silence_ms * 16, np.float32)))
    requests = []
    for pos in range(0, len(pcm), 800):
        requests.extend(segmenter.feed(AudioChunk(pcm[pos:pos + 800], pos + offset, 10 + (pos + offset) / 16000)))
    return requests, len(pcm)


def test_partial_then_final_preserves_all_samples_and_revisions():
    segmenter = Segmenter(Settings(), lambda f: bool(np.any(f)))
    requests, _ = feed_frames(segmenter, 1600, 600)
    assert requests and not requests[0].final and requests[-1].final
    assert requests[0].samples.size == 640 * 16
    assert [r.revision for r in requests] == list(range(1, len(requests) + 1))
    assert requests[-1].samples.size == 2000 * 16
    assert abs(requests[-1].speech_end_at - 11.6) < .001


def test_silence_never_triggers_recognition():
    segmenter = Segmenter(Settings(), lambda f: False)
    requests, _ = feed_frames(segmenter, 0, 10000)
    assert not requests


def test_continuous_speech_is_bounded_without_reusing_voiced_tail():
    segmenter = Segmenter(Settings(max_utterance_ms=2000), lambda f: bool(np.any(f)))
    requests, _ = feed_frames(segmenter, 4500, 600)
    finals = [r for r in requests if r.final]
    assert len(finals) == 3
    assert max(r.samples.size for r in requests) <= 2000 * 16
    assert abs(finals[1].started_at - finals[0].speech_end_at) < .001


def test_audio_discontinuity_discards_unfinished_phrase():
    segmenter = Segmenter(Settings(), lambda f: bool(np.any(f)))
    requests, size = feed_frames(segmenter, 800, 0)
    assert requests
    new, _ = feed_frames(segmenter, 800, 500, offset=size + 16000)
    assert segmenter.discontinuities == 1
    assert all(r.generation == 1 and r.utterance > requests[-1].utterance for r in new)
    assert max(r.samples.size for r in new) <= 1200 * 16


@dataclass
class Request:
    utterance: int
    revision: int
    final: bool = False


def test_mailbox_replaces_partials_and_counts_overload():
    mailbox = LatestMailbox(capacity=2)
    mailbox.put(Request(1, 1))
    mailbox.put(Request(1, 2, True))
    mailbox.put(Request(1, 1))
    mailbox.put(Request(2, 1, True))
    assert mailbox.get() == Request(1, 2, True)
    mailbox.put(Request(3, 1))
    mailbox.put(Request(4, 1))
    assert mailbox.dropped == 1
    assert mailbox.get().utterance == 3
    mailbox.close()
    assert mailbox.get() is None


def test_stop_wakes_waiting_worker():
    mailbox = LatestMailbox()
    stopped = threading.Event()
    thread = threading.Thread(target=lambda: (mailbox.get(), stopped.set()), daemon=True)
    thread.start()
    mailbox.close()
    assert stopped.wait(.5)
    thread.join(timeout=.5)


def test_resampler_keeps_state_across_small_blocks():
    wave = np.sin(np.arange(48000) * 2 * np.pi * 440 / 48000).astype(np.float32)
    whole = AudioResampler().convert(wave)
    resampler = AudioResampler()
    streamed = np.concatenate([resampler.convert(wave[i:i + 2400]) for i in range(0, len(wave), 2400)])
    assert streamed.dtype == np.float32
    assert 15900 <= len(streamed) <= 16000
    np.testing.assert_allclose(streamed, whole[:len(streamed)], atol=1e-5)
