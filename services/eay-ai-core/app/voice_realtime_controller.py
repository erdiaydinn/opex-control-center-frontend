from __future__ import annotations

import hashlib
import json
import secrets
from collections import deque
from dataclasses import dataclass
from typing import Deque, Literal

from .voice_streaming import VoiceStreamingOrchestrator

TaskKind = Literal["model", "tts", "tool"]
Risk = Literal["read", "write", "critical"]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MemoryTurn:
    role: Literal["user", "assistant", "tool"]
    content_sha256: str
    token_estimate: int
    fingerprint: str


class BoundedConversationMemory:
    """Hash-only bounded conversational memory metadata."""

    def __init__(self, *, max_turns: int = 24, max_token_estimate: int = 6000):
        if max_turns < 2 or max_turns > 200:
            raise ValueError("voice_memory_turn_limit_invalid")
        if max_token_estimate < 256 or max_token_estimate > 100000:
            raise ValueError("voice_memory_token_limit_invalid")
        self.max_turns = max_turns
        self.max_token_estimate = max_token_estimate
        self._turns: Deque[MemoryTurn] = deque()
        self._tokens = 0

    def append(self, *, role: str, text: str, token_estimate: int) -> MemoryTurn:
        if role not in {"user", "assistant", "tool"}:
            raise ValueError("voice_memory_role_invalid")
        normalized = " ".join(str(text or "").strip().split())
        if not normalized:
            raise ValueError("voice_memory_text_required")
        if token_estimate < 1:
            raise ValueError("voice_memory_token_estimate_invalid")
        content_sha = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        fp = _sha256({"role": role, "content_sha256": content_sha, "token_estimate": token_estimate})
        turn = MemoryTurn(role=role, content_sha256=content_sha, token_estimate=token_estimate, fingerprint=fp)
        self._turns.append(turn)
        self._tokens += token_estimate
        while len(self._turns) > self.max_turns or self._tokens > self.max_token_estimate:
            evicted = self._turns.popleft()
            self._tokens -= evicted.token_estimate
        return turn

    def snapshot(self) -> tuple[MemoryTurn, ...]:
        return tuple(self._turns)


@dataclass(frozen=True)
class ApprovalToken:
    token_id: str
    session_id: str
    tool_call_id: str
    risk: Risk
    intent_fingerprint: str
    token_sha256: str


class SingleUseApprovalStore:
    def __init__(self) -> None:
        self._tokens: dict[str, ApprovalToken] = {}
        self._used: set[str] = set()

    def issue(self, *, session_id: str, tool_call_id: str, risk: Risk, intent_fingerprint: str) -> tuple[str, ApprovalToken]:
        if risk not in {"write", "critical"}:
            raise ValueError("voice_approval_token_risk_invalid")
        if len(session_id.strip()) < 3 or len(tool_call_id.strip()) < 3:
            raise ValueError("voice_approval_token_identity_required")
        if len(intent_fingerprint) != 64:
            raise ValueError("voice_approval_token_intent_fingerprint_invalid")
        secret = secrets.token_urlsafe(32)
        token_sha = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        token_id = secrets.token_hex(12)
        record = ApprovalToken(
            token_id=token_id,
            session_id=session_id.strip(),
            tool_call_id=tool_call_id.strip(),
            risk=risk,
            intent_fingerprint=intent_fingerprint,
            token_sha256=token_sha,
        )
        self._tokens[token_id] = record
        return f"{token_id}.{secret}", record

    def consume(self, *, token: str, session_id: str, tool_call_id: str, risk: Risk, intent_fingerprint: str) -> ApprovalToken:
        try:
            token_id, secret = token.split(".", 1)
        except ValueError as exc:
            raise ValueError("voice_approval_token_malformed") from exc
        if token_id in self._used:
            raise ValueError("voice_approval_token_replay")
        record = self._tokens.get(token_id)
        if record is None:
            raise ValueError("voice_approval_token_unknown")
        if hashlib.sha256(secret.encode("utf-8")).hexdigest() != record.token_sha256:
            raise ValueError("voice_approval_token_secret_mismatch")
        if (
            record.session_id != session_id
            or record.tool_call_id != tool_call_id
            or record.risk != risk
            or record.intent_fingerprint != intent_fingerprint
        ):
            raise ValueError("voice_approval_token_binding_mismatch")
        self._used.add(token_id)
        self._tokens.pop(token_id, None)
        return record


@dataclass(frozen=True)
class ActiveTask:
    task_id: str
    kind: TaskKind
    cancellable: bool
    cancelled: bool = False


class VoiceRealtimeSessionController:
    """Single owner for cancellable model/TTS/tool work in one voice session."""

    def __init__(self, *, session_id: str, language: str):
        self.streaming = VoiceStreamingOrchestrator(session_id=session_id, language=language)
        self.memory = BoundedConversationMemory()
        self.approvals = SingleUseApprovalStore()
        self._tasks: dict[str, ActiveTask] = {}

    def start_task(self, *, task_id: str, kind: TaskKind, cancellable: bool = True) -> ActiveTask:
        task_id = task_id.strip()
        if len(task_id) < 3:
            raise ValueError("voice_realtime_task_id_required")
        if kind not in {"model", "tts", "tool"}:
            raise ValueError("voice_realtime_task_kind_invalid")
        if task_id in self._tasks and not self._tasks[task_id].cancelled:
            raise ValueError("voice_realtime_task_already_active")
        task = ActiveTask(task_id=task_id, kind=kind, cancellable=cancellable)
        self._tasks[task_id] = task
        return task

    def finish_task(self, *, task_id: str) -> ActiveTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise ValueError("voice_realtime_task_unknown")
        if task.cancelled:
            raise ValueError("voice_realtime_cancelled_task_cannot_finish")
        self._tasks.pop(task_id, None)
        return task

    def cancel_for_barge_in(self) -> tuple[ActiveTask, ...]:
        cancelled: list[ActiveTask] = []
        for task_id, task in list(self._tasks.items()):
            if task.cancelled or not task.cancellable:
                continue
            updated = ActiveTask(task_id=task.task_id, kind=task.kind, cancellable=task.cancellable, cancelled=True)
            self._tasks[task_id] = updated
            cancelled.append(updated)
        if self.streaming.snapshot().response_id is not None:
            self.streaming.barge_in()
        return tuple(cancelled)

    def active_tasks(self) -> tuple[ActiveTask, ...]:
        return tuple(task for task in self._tasks.values() if not task.cancelled)
