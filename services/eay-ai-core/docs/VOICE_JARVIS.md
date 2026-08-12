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
- Runtime binary bytes are independently attested before local adapter execution. A package/version label cannot stand in for an exact executable artifact.

## Production promotion

`VoiceAdapterPromotionRegistry` is the adapter promotion boundary. Promotion requires the exact model/voice artifact, profile fingerprint, separately allow-listed runtime and artifact licenses, production-eligible language capability fingerprints, reviewer identity and approval reference. Artifact, profile, license contract or language-eval drift fails closed.

`voice_runtime_attestation.py` adds a second execution boundary after promotion: the exact local runtime file is hashed, symlinks are rejected, candidate kind/implementation/runtime license must match the promoted adapter, and the resulting seal binds runtime bytes + model/voice bytes + promotion fingerprint + deployment manifest. This prevents replacing a reviewed runtime with different local bytes after promotion.

The default Jarvis profile intentionally contains `deployment-review-required` placeholders and therefore cannot be promoted. Deployment must select concrete local adapters, verify their current licenses from authoritative project/model sources, pin downloaded artifact hashes and run multilingual voice evals before promotion.

## Authoritative adapter candidates (verified 2026-08-12)

`voice_adapter_candidates.py` records the current safe discovery posture. It is not an auto-installer and it does not auto-promote any model.

- **STT — whisper.cpp + OpenAI Whisper**: whisper.cpp runtime is MIT and the OpenAI Whisper repository states code/model weights are MIT. Candidate status: `eligible_with_pinned_artifact`. Official sources: `https://github.com/ggml-org/whisper.cpp`, `https://github.com/openai/whisper`.
- **VAD — Silero VAD ONNX**: project/runtime is MIT and supports local ONNX execution. Candidate status: `eligible_with_pinned_artifact`. Official source: `https://github.com/snakers4/silero-vad`.
- **Wake word — openWakeWord**: code is Apache-2.0, but bundled pretrained models are CC BY-NC-SA 4.0. Upstream currently documents English language support. EAY therefore neither uses bundled models commercially nor claims TR/DE/AR/FA support from this candidate. Candidate status: `custom_artifact_required`; broader language coverage requires separately licensed custom artifacts plus explicit multilingual evaluation. Official source: `https://github.com/dscripka/openWakeWord`.
- **TTS — sherpa-onnx + reviewed VITS/Piper voice artifact**: sherpa-onnx runtime is Apache-2.0 and supports local TTS/VAD/STT execution. Piper voice licenses can differ by model, so each selected voice artifact requires its own license review and hash pin. Candidate status: `per_artifact_review_required`. Official sources: `https://github.com/k2-fsa/sherpa-onnx`, `https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md`.

The current Piper engine itself is GPL-3.0 and is not in EAY's default permissive runtime-license allow-list. EAY therefore keeps the Apache-2.0 sherpa-onnx inference path as the candidate runtime and still requires every selected voice model's own license to be allow-listed.

## RAM-only audio data plane

`VoiceAudioDataPlane` is separate from the persisted WebSocket/audit control plane. Raw PCM is accepted only as an owned mutable `bytearray`, sequence/sample shape/backpressure are validated, and audit-facing receipts expose only SHA-256 metadata. VAD can inspect buffered frames through short-lived read-only memory views without consuming the utterance. STT consumes the selected frames once and the data plane overwrites the owned bytearrays afterward, including error paths. `close()`/`discard_all()` also overwrite remaining owned buffers.

This is a best-effort application-memory boundary, not a claim that Python, native libraries or the operating system can erase every copy they may internally create. Executable adapters must therefore remain local and must not persist or transmit audio outside the governed runtime.

`PinnedLocalVadAdapter` and `PinnedLocalSttAdapter` are the in-memory adapter boundary. They require a validated runtime-artifact seal and the same deployment manifest as the audio data plane. VAD returns only probability/hash lineage and deliberately leaves audio buffered for STT. STT returns transient text to the caller while its provenance/audit identity is the text SHA-256; raw transcript text is not part of the sealed execution fingerprint.

## Concrete native VAD and STT engines

`voice_native_engines.py` now implements the first real local execution path rather than only Protocol interfaces.

- `SileroOnnxVadEngine` re-hashes the exact ONNX model before session construction, requires the current upstream `input/state/sr` contract, uses CPU ONNX Runtime locally and passes PCM directly from RAM. EAY uses exact 512-sample windows at 16 kHz, matching the upstream streaming wrapper contract. Recurrent state/context are recreated per governed score call so raw utterance context is not retained across callbacks.
- `WhisperCppSttEngine` passes PCM16 directly in memory to an EAY-owned stable C ABI shim. The shim uses whisper.cpp's public `whisper_full()` PCM API rather than creating a temporary WAV file. The exact model and exact shim shared-library bytes are re-hashed before execution.
- `native/eay_whisper_shim.cpp` must be built with whisper.cpp statically linked into the attested shared-library artifact. A separately drifting dynamic libwhisper is not an eligible production build because its bytes would not be covered by the runtime seal.
- The optional `voice-onnx` dependency group contains NumPy + ONNX Runtime for the concrete Silero path. Production still requires exact downloaded model hashes, promotion evidence and runtime attestation; installing an optional dependency alone grants no production eligibility.

`VoiceLocalInputPipeline` composes the RAM data plane, frame-by-frame `VoiceInputLineageTracker`, pinned VAD, pinned STT and transient transcript handling. It requires speech to have been detected before finalization, consumes/wipes all utterance PCM through STT, and returns a hash-only end-to-end utterance proof binding wake proof, microphone chain, VAD result, STT result, STT runtime seal and text SHA-256.

## Privacy-preserving session audit

`VoiceSessionLedger` creates an append-only SHA-256 chain for wake, utterance, tool, approval, response and interruption events. It rejects raw-audio/transcript metadata and requires tool-call IDs and explicit approval references where applicable. This provides incident/audit lineage without silently creating a raw voice recording store.

## Current runtime state

The governed runtime now includes WebSocket sequencing/replay protection, bounded conversation memory, full-duplex/barge-in cancellation, single-use approval tokens, tool execution provenance, deployment freshness checks, model/TTS response lineage, microphone-to-STT hash lineage, a bounded RAM-only PCM data plane, exact runtime-binary attestation, concrete Silero ONNX VAD, an in-memory whisper.cpp C-ABI STT path, and an end-to-end local microphone/VAD/STT coordinator.

The next implementation layer is production packaging and voice output: build reproducible hash-pinned native artifacts for the Silero/whisper paths, bind them to deployment startup without auto-downloading models, then implement per-language TTS artifact bundles for TR/EN/DE/AR/FA. Wake-word remains custom-artifact gated. No adapter becomes production-ready until real latency, accuracy/naturalness, barge-in and multilingual consistency evals pass the existing human-gated release path.
