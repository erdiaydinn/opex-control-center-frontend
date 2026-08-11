# EAY Jarvis Voice Runtime

EAY Jarvis is a local-first conversational runtime, not a voice-cloning feature. The target experience is natural, interruptible, multilingual conversation with tool use and proactive read-only suggestions while preserving explicit approval boundaries for side effects.

## Core runtime invariants

- Core voice languages are Turkish, English, German, Arabic and Persian; Arabic/Persian are RTL-aware.
- Wake word, VAD, STT and TTS remain replaceable adapters.
- Production adapters must be local, streaming, pinned to exact artifact SHA-256 values and use an allow-listed license.
- A contract-only adapter name is never executable by itself.
- Exact language capability fingerprints are sealed into each adapter promotion. A changed language eval invalidates the old promotion.
- Reference/proprietary voice cloning is forbidden by the voice profile contract. EAY uses its own voice identity.
- Write and critical actions require an explicit approval reference. Read-only context may be used proactively under the proactive-suggestion policy.
- Raw microphone bytes and transcript text are not written to the voice session audit ledger. The ledger persists transcript hashes and a chained event fingerprint only.
- Barge-in/interruption is a first-class state transition so a user can stop speech immediately.

## Production promotion

`VoiceAdapterPromotionRegistry` is the executable-adapter boundary. Promotion requires the exact adapter artifact, profile fingerprint, commercial-license allow-list check, production-eligible language capability fingerprints, reviewer identity and approval reference. Artifact, profile or language-eval drift fails closed.

The default Jarvis profile intentionally contains `deployment-review-required` placeholders and therefore cannot be promoted. Deployment must select concrete local adapters, verify their current licenses from authoritative project/model sources, pin downloaded artifact hashes and run multilingual voice evals before promotion.

## Privacy-preserving session audit

`VoiceSessionLedger` creates an append-only SHA-256 chain for wake, utterance, tool, approval, response and interruption events. It rejects raw-audio/transcript metadata and requires tool-call IDs and explicit approval references where applicable. This provides incident/audit lineage without silently creating a raw voice recording store.

## Remaining runtime work

The next implementation layer is the actual audio-frame/WebSocket orchestrator: streaming adapter interfaces, audio frame sequencing, wake/VAD lifecycle, STT partial/final events, EAY tool router integration, streaming TTS chunks, cancellation/barge-in propagation, bounded conversational memory and the existing release/eval gates.
