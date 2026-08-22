import threading
import time
from datetime import datetime, timezone

import pytest

from app.local_voice_playback import ThreadedLocalPlaybackBackend
from app.local_voice_runtime import TransientSpeechAudio

NOW = datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc)


class _Sink:
    local_device_ref = "device://local-speaker"

    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.audio_bytes_seen = 0

    def play(self, audio, *, stop_event):
        self.audio_bytes_seen = len(audio.pcm16)
        self.started.set()
        stop_event.wait(timeout=2.0)
        if stop_event.is_set():
            self.stopped.set()


def _audio():
    return TransientSpeechAudio(
        pcm16=b"\x01\x00" * 320,
        sample_rate_hz=24000,
    )


def test_threaded_playback_is_local_interruptible_and_receipt_retains_no_audio():
    sink = _Sink()
    backend = ThreadedLocalPlaybackBackend(sink=sink)
    handle = backend.start(_audio(), started_at=NOW)
    assert sink.started.wait(timeout=1.0)
    assert handle.active is True
    assert handle.audio_retained is False
    stopped = backend.stop(handle.playback_ref)
    assert stopped.active is False
    assert sink.stopped.wait(timeout=1.0)
    assert sink.audio_bytes_seen > 0
    assert "0100" not in stopped.model_dump_json()


def test_only_one_active_playback_is_allowed():
    sink = _Sink()
    backend = ThreadedLocalPlaybackBackend(sink=sink)
    handle = backend.start(_audio(), started_at=NOW)
    assert sink.started.wait(timeout=1.0)
    with pytest.raises(RuntimeError, match="already_active"):
        backend.start(_audio(), started_at=NOW)
    backend.stop(handle.playback_ref)
    assert sink.stopped.wait(timeout=1.0)


def test_unknown_playback_ref_fails_closed():
    sink = _Sink()
    backend = ThreadedLocalPlaybackBackend(sink=sink)
    with pytest.raises(KeyError, match="ref_not_active"):
        backend.stop("playback://local/missing")
