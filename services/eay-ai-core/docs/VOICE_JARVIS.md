# EAY Jarvis Voice Runtime

EAY Jarvis is a local-first conversational runtime, not a voice-cloning feature. The target experience is natural, interruptible, multilingual conversation with tool use and proactive read-only suggestions while preserving explicit approval boundaries for side effects.

## Core runtime invariants

- Core voice languages are Turkish, English, German, Arabic and Persian; Arabic/Persian are RTL-aware.
- Wake word, VAD, STT and TTS remain replaceable adapters.
- Production adapters must be local, streaming, pinned to exact artifact SHA-256 values and use allow-listed licenses.
- Runtime-code licensing and downloaded model/voice-artifact licensing are checked independently. A permissive engine never implicitly authorizes restrictive model weights.
- A contract-only adapter name is never executable by itself.
- Exact language capability fingerprints are sealed into each adapter promotion. A changed language eval invalidates the old promotion.
- Reference/proprietary voice cloning is forbidden by the voice profile contract. EAY uses its own voice identity.
- Write and critical actions require an explicit approval reference. Read-only context may be used proactively under the proactive-suggestion policy.
- Raw microphone bytes and transcript text are not written to the voice session audit ledger. The ledger persists transcript hashes and a chained event fingerprint only.
- Barge-in/interruption is a first-class state transition so a user can stop speech immediately.
- Every session is pinned to one verified deployment manifest; response/TTS results are revalidated against that deployment before acceptance.
- Wake/VAD/STT input lineage is SHA-256 chained into the response proof without persisting raw microphone audio.

## Production promotion

`VoiceAdapterPromotionRegistry` is the executable-adapter boundary. Promotion requires the exact adapter artifact, profile fingerprint, separately allow-listed runtime and artifact licenses, production-eligible language capability fingerprints, reviewer identity and approval reference. Artifact, profile, license contract or language-eval drift fails closed.

The default Jarvis profile intentionally contains `deployment-review-required` placeholders and therefore cannot be promoted. Deployment must select concrete local adapters, verify their current licenses from authoritative project/model sources, pin downloaded artifact hashes and run multilingual voice evals before promotion.

## Authoritative adapter candidates (verified 2026-08-12)

`voice_adapter_candidates.py` records the current safe discovery posture. It is not an auto-installer and it does not auto-promote any model.

- **STT — whisper.cpp + OpenAI Whisper**: whisper.cpp runtime is MIT and the OpenAI Whisper repository states code/model weights are MIT. Candidate status: `eligible_with_pinned_artifact`. Official sources: `https://github.com/ggml-org/whisper.cpp`, `https://github.com/openai/whisper`.
- **VAD — Silero VAD ONNX**: project/runtime is MIT and supports local ONNX execution. Candidate status: `eligible_with_pinned_artifact`. Official source: `https://github.com/snakers4/silero-vad`.
- **Wake word — openWakeWord**: code is Apache-2.0, but the project's bundled pretrained wake-word models are CC BY-NC-SA 4.0. EAY therefore forbids implicit use of those bundled models in a commercial deployment. Candidate status: `custom_artifact_required`; a separately licensed custom EAY wake-word artifact must be reviewed and hash-pinned. Official source: `https://github.com/dscripka/openWakeWord`.
- **TTS — sherpa-onnx + reviewed VITS/Piper voice artifact**: sherpa-onnx runtime is Apache-2.0 and supports VITS/Piper TTS. Piper's current voices catalog includes Turkish, English, German, Arabic and Persian, but explicitly requires checking each voice `MODEL_CARD` because voice licenses can differ. Candidate status: `per_artifact_review_required`. Official sources: `https://github.com/k2-fsa/sherpa-onnx`, `https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md`.

The current Piper engine itself is GPL-3.0 and is not in EAY's default permissive runtime-license allow-list. EAY therefore uses the Apache-2.0 sherpa-onnx inference path as the candidate runtime and still requires the selected voice model's own license to be allow-listed. This is a deliberate commercial-license isolation boundary, not a claim that all Piper voice weights are permissively licensed.

## Privacy-preserving session audit

`VoiceSessionLedger` creates an append-only SHA-256 chain for wake, utterance, tool, approval, response and interruption events. It rejects raw-audio/transcript metadata and requires tool-call IDs and explicit approval references where applicable. This provides incident/audit lineage without silently creating a raw voice recording store.

## Current runtime state

The governed runtime now includes WebSocket sequencing/replay protection, bounded conversation memory, full-duplex/barge-in cancellation, single-use approval tokens, tool execution provenance, deployment freshness checks, model/TTS response lineage, and microphone-to-STT input lineage.

The next implementation layer is the **actual in-memory audio data plane and executable local adapters**. Raw PCM must remain outside the persisted WebSocket control/audit plane while being made available transiently to promoted wake/VAD/STT adapters. The first executable path should use exact binary/model hashes and fail closed if bytes, license posture, deployment manifest or multilingual eval lineage drift. TTS voice artifacts must remain per-voice reviewed; no automatic model download may create a production-eligible adapter.
