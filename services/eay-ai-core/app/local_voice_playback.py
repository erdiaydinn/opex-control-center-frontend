"""Interruptible local playback coordinator for Jarvis voice.

The coordinator is backend-neutral and keeps generated PCM transient. A device
sink owns the actual local audio API (for example a future WASAPI field adapter)
and must honor the stop signal. This avoids coupling the core to legacy Windows
PlaySound semantics or a mandatory third-party audio package.
"""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime
from typing import Protocol

from .local_voice_runtime import LocalPlaybackHandle, TransientSpeechAudio

LOCAL_VOICE_PLAYBACK_CONTRACT = "eay-local-voice-playback-v1"


class InterruptiblePcmSink(Protocol):
    local_device_ref: str

    def play(self, audio: TransientSpeechAudio, *, stop_event: threading.Event) -> None: ...


class ThreadedLocalPlaybackBackend:
    """One active in-memory playback, interruptible through a local stop event."""

    def __init__(self, *, sink: InterruptiblePcmSink) -> None:
        if not sink.local_device_ref.strip():
            raise ValueError("local_voice_playback_device_ref_required")
        self._sink = sink
        self._lock = threading.Lock()
        self._active_ref: str | None = None
        self._active_started_at: datetime | None = None
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._counter = 0

    def _run(self, audio: TransientSpeechAudio, stop_event: threading.Event) -> None:
        try:
            self._sink.play(audio, stop_event=stop_event)
        finally:
            # Do not retain audio or mutate another playback's state.
            with self._lock:
                if self._stop_event is stop_event:
                    self._active_ref = None
                    self._active_started_at = None
                    self._stop_event = None
                    self._thread = None

    def start(self, audio: TransientSpeechAudio, *, started_at: datetime) -> LocalPlaybackHandle:
        if started_at.tzinfo is None or started_at.utcoffset() is None:
            raise ValueError("local_voice_playback_requires_timezone")
        with self._lock:
            if self._active_ref is not None:
                raise RuntimeError("local_voice_playback_already_active")
            self._counter += 1
            digest = hashlib.sha256(
                f"{self._sink.local_device_ref}|{started_at.isoformat()}|{self._counter}".encode("utf-8")
            ).hexdigest()[:24]
            playback_ref = f"playback://local/{digest}"
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._run,
                args=(audio, stop_event),
                name="eay-local-voice-playback",
                daemon=True,
            )
            self._active_ref = playback_ref
            self._active_started_at = started_at
            self._stop_event = stop_event
            self._thread = thread
            thread.start()
        return LocalPlaybackHandle(
            playback_ref=playback_ref,
            started_at=started_at,
            local_device_ref=self._sink.local_device_ref,
            active=True,
        )

    def stop(self, playback_ref: str) -> LocalPlaybackHandle:
        with self._lock:
            if self._active_ref != playback_ref or self._stop_event is None or self._active_started_at is None:
                raise KeyError("local_voice_playback_ref_not_active")
            stop_event = self._stop_event
            started_at = self._active_started_at
            stop_event.set()
        return LocalPlaybackHandle(
            playback_ref=playback_ref,
            started_at=started_at,
            local_device_ref=self._sink.local_device_ref,
            active=False,
        )
