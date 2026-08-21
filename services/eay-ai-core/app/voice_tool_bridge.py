from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Mapping

from .voice_session_ledger import VoiceSessionLedger

VoiceToolRisk = Literal["read", "write", "critical"]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceToolIntent:
    session_id: str
    language: str
    tool_name: str
    tool_call_id: str
    risk: VoiceToolRisk
    arguments_sha256: str
    reason_sha256: str
    approval_reference: str | None
    fingerprint: str


class VoiceToolBridge:
    """Bind voice-originated tool intents to explicit approval and audit lineage.

    The bridge does not execute a tool. It produces a sealed intent that downstream
    reviewed tool execution may consume. Read-only calls can be sealed directly;
    write/critical calls require an explicit approval reference and both request and
    approval are appended to the privacy-preserving voice session ledger.
    """

    def __init__(self, ledger: VoiceSessionLedger):
        self.ledger = ledger

    def seal_intent(
        self,
        *,
        session_id: str,
        language: str,
        tool_name: str,
        tool_call_id: str,
        risk: VoiceToolRisk,
        arguments: Mapping[str, object],
        reason: str,
        approval_reference: str | None = None,
    ) -> VoiceToolIntent:
        session_id = session_id.strip()
        language = language.strip().lower()
        tool_name = tool_name.strip()
        tool_call_id = tool_call_id.strip()
        reason = reason.strip()
        approval_reference = (approval_reference or "").strip() or None

        if len(session_id) < 3:
            raise ValueError("voice_tool_session_id_required")
        if not language:
            raise ValueError("voice_tool_language_required")
        if len(tool_name) < 3:
            raise ValueError("voice_tool_name_required")
        if len(tool_call_id) < 3:
            raise ValueError("voice_tool_call_id_required")
        if risk not in {"read", "write", "critical"}:
            raise ValueError("voice_tool_risk_invalid")
        if len(reason) < 3:
            raise ValueError("voice_tool_reason_required")
        if risk in {"write", "critical"} and approval_reference is None:
            self.ledger.append(
                session_id=session_id,
                event_type="approval_required",
                language=language,
                action_risk=risk,
                tool_call_id=tool_call_id,
                metadata={"tool_name_sha256": hashlib.sha256(tool_name.encode()).hexdigest()},
            )
            raise ValueError("voice_tool_explicit_approval_required")

        args_sha = _sha256(dict(arguments))
        reason_sha = hashlib.sha256(reason.encode("utf-8")).hexdigest()
        self.ledger.append(
            session_id=session_id,
            event_type="tool_request",
            language=language,
            action_risk=risk,
            tool_call_id=tool_call_id,
            metadata={
                "tool_name_sha256": hashlib.sha256(tool_name.encode("utf-8")).hexdigest(),
                "arguments_sha256": args_sha,
                "reason_sha256": reason_sha,
            },
        )
        if risk in {"write", "critical"}:
            self.ledger.append(
                session_id=session_id,
                event_type="approval_granted",
                language=language,
                action_risk=risk,
                tool_call_id=tool_call_id,
                approval_reference=approval_reference,
                metadata={"tool_name_sha256": hashlib.sha256(tool_name.encode()).hexdigest()},
            )

        payload = {
            "session_id": session_id,
            "language": language,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "risk": risk,
            "arguments_sha256": args_sha,
            "reason_sha256": reason_sha,
            "approval_reference": approval_reference,
        }
        return VoiceToolIntent(
            session_id=session_id,
            language=language,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            risk=risk,
            arguments_sha256=args_sha,
            reason_sha256=reason_sha,
            approval_reference=approval_reference,
            fingerprint=_sha256(payload),
        )
