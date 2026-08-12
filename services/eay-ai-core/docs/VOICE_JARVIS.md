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
- Raw microphone bytes and transcript text are not written to the voice control-plane or session audit lineage. Hash-only provenance is used instead.
- Barge-in/interruption is a first-class state transition so a user can stop speech immediately.

## Production deployment manifest

`VoiceRuntimeDeploymentManifest` seals the current production model promotion, model release proof, exact model artifact, voice profile and the promoted wakeword/VAD/STT/TTS adapter identities into one immutable SHA-256 deployment fingerprint.

Production startup must use `configure_verified_voice_deployment`; it rebuilds the manifest from current registries rather than trusting caller-authored fingerprints. The resulting server-owned execution binding pins the exact model/TTS execution identities plus wakeword, VAD and STT identities used by the session.

A WebSocket session is pinned to one deployment manifest at bootstrap. New turns, response generation, TTS starts and async task-result acceptance revalidate that manifest. If production model lineage, evaluation lineage, adapter artifact, profile or adapter promotion changes while a task is running, the stale result fails closed instead of entering conversation memory or speech output.

## Microphone-to-response lineage

`VoiceInputLineageTracker` creates a hash-only chain from wake detection through audio frames and final STT output:

1. The wake proof binds session/language to the exact wakeword deployment identity.
2. Every audio-frame proof binds frame sequence, PCM SHA-256, duration and sample rate to the exact VAD identity and previous audio-chain fingerprint.
3. The final STT proof binds the rolling audio chain to the exact STT identity and transcript SHA-256.
4. The model response proof includes that exact STT input-lineage fingerprint together with governed tool/legal/KPI evidence, deployment manifest and model execution identity.
5. TTS is authorized only from the matching response proof and exact promoted TTS identity.

This makes the intended runtime lineage deterministic from microphone ingress to spoken output without persisting raw voice or transcript content.

## Governed tools and approvals

Voice tool intents are sealed before execution. Read-only tools may execute without a side-effect approval token, while write/critical actions require a single-use token bound to session, tool-call ID, risk class and exact intent fingerprint. Tool results must carry governed execution provenance; raw adapter strings are not accepted as execution results.

Barge-in advances the turn epoch and cancels eligible model/TTS/tool tasks. Results from a cancelled or older epoch are rejected. The same freshness check is repeated after async tool adapters return, so deployment drift during a long-running operation cannot be accepted after the fact.

## Privacy-preserving session audit

`VoiceSessionLedger` creates an append-only SHA-256 chain for wake, utterance, tool, approval, response and interruption events. It rejects raw-audio/transcript metadata and requires tool-call IDs and explicit approval references where applicable. Response/TTS proof metadata includes deployment and evidence lineage fingerprints rather than raw content.

## Release requirements

The multilingual voice release gate evaluates STT quality, semantic consistency, naturalness, citation readback, first-audio latency, interruption success, cancellation latency and approval-replay security. A weak core language prevents the deployment from being labelled multilingual-ready.

Remaining runtime work is primarily concrete local adapter integration and production measurement: streaming STT/TTS implementations, wake/VAD binaries, real multilingual eval corpora, end-to-end latency/load testing, device/audio-driver integration and deployment-specific license/artifact verification.
