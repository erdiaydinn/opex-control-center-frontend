from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .voice_realtime_controller import VoiceRealtimeSessionController
from .voice_session_ledger import VoiceSessionLedger
from .voice_tool_bridge import VoiceToolIntent


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class AsyncSttAdapter(Protocol):
    async def transcribe(self, *, frame_sha256: str, cancellation: "CancellationToken") -> str: ...


class AsyncModelAdapter(Protocol):
    async def generate(self, *, input_sha256: str, cancellation: "CancellationToken") -> str: ...


class AsyncTtsAdapter(Protocol):
    async def synthesize(self, *, text_sha256: str, cancellation: "CancellationToken") -> str: ...


class AsyncToolAdapter(Protocol):
    async def execute(self, *, intent: VoiceToolIntent, cancellation: "CancellationToken") -> str: ...


@dataclass
class CancellationToken:
    task_id: str
    turn_epoch: int
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True

    def checkpoint(self) -> None:
        if self.cancelled:
            raise RuntimeError("voice_async_task_cancelled")


@dataclass(frozen=True)
class TaskLease:
    task_id: str
    kind: str
    turn_epoch: int
    request_fingerprint: str


@dataclass(frozen=True)
class AcceptedAsyncResult:
    task_id: str
    kind: str
    turn_epoch: int
    result_sha256: str
    request_fingerprint: str
    fingerprint: str


class VoiceAsyncExecutionCoordinator:
    """Own async voice work and prevent late results from crossing turn boundaries."""

    def __init__(
        self,
        *,
        controller: VoiceRealtimeSessionController,
        ledger: VoiceSessionLedger | None = None,
    ) -> None:
        self.controller = controller
        self.ledger = ledger
        self._turn_epoch = 0
        self._leases: dict[str, TaskLease] = {}
        self._tokens: dict[str, CancellationToken] = {}
        self._accepted: set[str] = set()

    @property
    def turn_epoch(self) -> int:
        return self._turn_epoch

    def start_turn(self) -> int:
        if self.controller.active_tasks():
            raise ValueError("voice_async_active_tasks_require_cancellation")
        self._turn_epoch += 1
        return self._turn_epoch

    def start_task(
        self,
        *,
        task_id: str,
        kind: str,
        request_fingerprint: str,
        cancellable: bool = True,
    ) -> tuple[TaskLease, CancellationToken]:
        if len(request_fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in request_fingerprint):
            raise ValueError("voice_async_request_fingerprint_invalid")
        if self._turn_epoch < 1:
            raise ValueError("voice_async_turn_required")
        self.controller.start_task(task_id=task_id, kind=kind, cancellable=cancellable)
        lease = TaskLease(
            task_id=task_id,
            kind=kind,
            turn_epoch=self._turn_epoch,
            request_fingerprint=request_fingerprint,
        )
        token = CancellationToken(task_id=task_id, turn_epoch=self._turn_epoch)
        self._leases[task_id] = lease
        self._tokens[task_id] = token
        return lease, token

    def lease_for(self, task_id: str) -> TaskLease:
        lease = self._leases.get(task_id.strip())
        if lease is None:
            raise ValueError("voice_async_task_lease_missing")
        return lease

    def cancel_for_barge_in(self) -> tuple[str, ...]:
        cancelled = self.controller.cancel_for_barge_in()
        cancelled_ids = tuple(sorted(task.task_id for task in cancelled))
        for task_id in cancelled_ids:
            token = self._tokens.get(task_id)
            if token is not None:
                token.cancel()
        self._turn_epoch += 1
        if self.ledger is not None:
            self.ledger.append(
                session_id=self.controller.streaming.session_id,
                event_type="interrupted",
                language=self.controller.streaming.language,
                metadata={
                    "cancelled_task_ids_sha256": _sha256(cancelled_ids),
                    "new_turn_epoch": self._turn_epoch,
                },
            )
        return cancelled_ids

    def accept_result(self, *, lease: TaskLease, result_sha256: str) -> AcceptedAsyncResult:
        if len(result_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in result_sha256):
            raise ValueError("voice_async_result_fingerprint_invalid")
        current = self._leases.get(lease.task_id)
        if current != lease:
            raise ValueError("voice_async_task_lease_mismatch")
        token = self._tokens.get(lease.task_id)
        if token is None:
            raise ValueError("voice_async_task_token_missing")
        if token.cancelled:
            raise ValueError("voice_async_cancelled_result_rejected")
        if lease.turn_epoch != self._turn_epoch:
            raise ValueError("voice_async_stale_turn_result_rejected")
        if lease.task_id in self._accepted:
            raise ValueError("voice_async_duplicate_result_rejected")
        active_ids = {task.task_id for task in self.controller.active_tasks()}
        if lease.task_id not in active_ids:
            raise ValueError("voice_async_inactive_task_result_rejected")
        payload = {
            "task_id": lease.task_id,
            "kind": lease.kind,
            "turn_epoch": lease.turn_epoch,
            "result_sha256": result_sha256,
            "request_fingerprint": lease.request_fingerprint,
        }
        accepted = AcceptedAsyncResult(**payload, fingerprint=_sha256(payload))
        self._accepted.add(lease.task_id)
        self.controller.finish_task(task_id=lease.task_id)
        return accepted

    def authorize_tool_execution(self, *, intent: VoiceToolIntent, approval_token: str | None = None) -> None:
        if intent.session_id != self.controller.streaming.session_id:
            raise ValueError("voice_async_tool_session_mismatch")
        if intent.risk == "read":
            if approval_token is not None:
                raise ValueError("voice_async_read_approval_token_forbidden")
            return
        if approval_token is None:
            raise ValueError("voice_async_tool_approval_token_required")
        self.controller.approvals.consume(
            token=approval_token,
            session_id=intent.session_id,
            tool_call_id=intent.tool_call_id,
            risk=intent.risk,
            intent_fingerprint=intent.fingerprint,
        )

    async def execute_tool(
        self,
        *,
        intent: VoiceToolIntent,
        approval_token: str | None,
        adapter: AsyncToolAdapter,
        lease: TaskLease,
        cancellation: CancellationToken,
    ) -> AcceptedAsyncResult:
        self.authorize_tool_execution(intent=intent, approval_token=approval_token)
        cancellation.checkpoint()
        raw_result = await adapter.execute(intent=intent, cancellation=cancellation)
        cancellation.checkpoint()
        result_sha = hashlib.sha256(str(raw_result).encode("utf-8")).hexdigest()
        accepted = self.accept_result(lease=lease, result_sha256=result_sha)
        if self.ledger is not None:
            self.ledger.append(
                session_id=intent.session_id,
                event_type="tool_result",
                language=intent.language,
                action_risk=intent.risk,
                tool_call_id=intent.tool_call_id,
                approval_reference=intent.approval_reference,
                metadata={
                    "intent_fingerprint": intent.fingerprint,
                    "result_sha256": accepted.result_sha256,
                    "accepted_result_fingerprint": accepted.fingerprint,
                    "turn_epoch": accepted.turn_epoch,
                },
            )
        return accepted
