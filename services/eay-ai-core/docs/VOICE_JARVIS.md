# EAY Jarvis Voice Runtime

EAY Jarvis is a local-first conversational runtime, not a voice-cloning feature. The target experience is natural, interruptible, multilingual conversation with tool use and proactive read-only suggestions while preserving explicit approval boundaries for side effects.

## Core runtime invariants

- Core voice languages are Turkish, English, German, Arabic and Persian; Arabic/Persian are RTL-aware.
- Wake word, VAD, STT and TTS remain replaceable adapters.
- Production adapters must be local, streaming, pinned to exact artifact SHA-256 values and use allow-listed licenses.
- Runtime-code licensing and downloaded model/voice/resource licensing are checked independently. A permissive engine never implicitly authorizes restrictive model weights or runtime resources.
- A contract-only adapter name is never executable by itself.
- Exact language capability fingerprints are sealed into each adapter promotion. A changed language eval invalidates the old promotion.
- Reference/proprietary voice cloning is forbidden by the voice profile contract. EAY uses its own voice identity.
- Write and critical actions require an explicit approval reference. Read-only context may be used proactively under the proactive-suggestion policy.
- Raw microphone bytes and transcript text are not written to the voice session audit ledger. The ledger persists transcript hashes and a chained event fingerprint only.
- Barge-in/interruption is a first-class state transition so a user can stop speech immediately.
- Every session is pinned to one verified deployment manifest; response/TTS results are revalidated against that deployment before acceptance.
- Wake/VAD/STT input lineage is SHA-256 chained into the response proof without persisting raw microphone audio.
- Runtime binary bytes and shared runtime-resource directories are independently attested before local adapter execution. A package/version label cannot stand in for exact executable/resource bytes.
- Production WebSocket sessions fail closed unless the exact deployment has an approved multilingual release decision and a matching full runtime-attestation bundle.

## Production promotion

`VoiceAdapterPromotionRegistry` is the adapter promotion boundary. Promotion requires the exact model/voice artifact, profile fingerprint, separately allow-listed runtime and artifact licenses, production-eligible language capability fingerprints, reviewer identity and approval reference. Artifact, profile, license contract or language-eval drift fails closed.

`voice_runtime_attestation.py` adds a second execution boundary after promotion. Exact local runtime files are hashed and symlinks are rejected. Deterministic directory manifests hash every regular resource file by sorted POSIX-relative path while excluding host-local root paths and mtimes. Nested symlinks, traversal errors, file-count overflow and byte-limit overflow fail closed. This is used for shared native resources such as phonemizer data so a partial or redirected resource tree cannot masquerade as the reviewed deployment.

`voice_runtime_attestation_bundle.py` closes the aggregate-runtime gap. It requires exact wake-word, VAD, STT and TTS runtime seals; verifies each nested seal's canonical fingerprint; binds every seal to the matching promoted adapter deployment identity; requires all four seals to reference the same deployment manifest; and binds the exact promoted per-language TTS bundle. Missing/duplicate kinds, artifact/promotion/profile drift or a runtime seal that does not belong to the manifest fails closed.

The default Jarvis profile intentionally contains `deployment-review-required` placeholders and therefore cannot be promoted. Deployment must select concrete local adapters, verify their current licenses from authoritative project/model sources, pin downloaded artifact hashes and run multilingual voice evals before promotion.

## Authoritative adapter candidates (verified 2026-08-12)

`voice_adapter_candidates.py` records the current safe discovery posture. It is not an auto-installer and it does not auto-promote any model.

- **STT — whisper.cpp + OpenAI Whisper**: whisper.cpp runtime is MIT and the OpenAI Whisper repository states code/model weights are MIT. Candidate status: `eligible_with_pinned_artifact`. Official sources: `https://github.com/ggml-org/whisper.cpp`, `https://github.com/openai/whisper`.
- **VAD — Silero VAD ONNX**: project/runtime is MIT and supports local ONNX execution. Candidate status: `eligible_with_pinned_artifact`. Official source: `https://github.com/snakers4/silero-vad`.
- **Wake word — openWakeWord**: code is Apache-2.0, but bundled pretrained models are CC BY-NC-SA 4.0. Upstream currently documents English language support. EAY therefore neither uses bundled models commercially nor claims TR/DE/AR/FA support from this candidate. Candidate status: `custom_artifact_required`; broader language coverage requires separately licensed custom artifacts plus explicit multilingual evaluation. Official source: `https://github.com/dscripka/openWakeWord`.
- **TTS — sherpa-onnx + reviewed VITS/Piper voice artifact**: sherpa-onnx runtime is Apache-2.0 and supports local TTS/VAD/STT execution. Piper voice licenses can differ by model, so each selected voice artifact requires its own license review and hash pin. Converted Piper/VITS execution also depends on exact tokens and shared phonemizer data. Candidate status: `per_artifact_review_required`. Official sources: `https://github.com/k2-fsa/sherpa-onnx`, `https://k2-fsa.github.io/sherpa/onnx/tts/piper.html`, `https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md`.

The current Piper engine itself is GPL-3.0 and is not in EAY's default permissive runtime-license allow-list. EAY therefore keeps the Apache-2.0 sherpa-onnx inference path as the candidate runtime and still requires every selected voice model and shared phonemizer resource license to be reviewed independently. The current default EAY allow-list is intentionally fail-closed for GPL-tagged phonemizer resources; that is a compliance gate, not a statement that GPL software is inherently non-commercial.

## RAM-only audio data plane

`VoiceAudioDataPlane` is separate from the persisted WebSocket/audit control plane. Raw PCM is accepted only as an owned mutable `bytearray`, sequence/sample shape/backpressure are validated, and audit-facing receipts expose only SHA-256 metadata. VAD can inspect buffered frames through short-lived read-only memory views without consuming the utterance. STT consumes the selected frames once and the data plane overwrites the owned bytearrays afterward, including error paths. `close()`/`discard_all()` also overwrite remaining owned buffers.

This is a best-effort application-memory boundary, not a claim that Python, native libraries or the operating system can erase every copy they may internally create. Executable adapters must therefore remain local and must not persist or transmit audio outside the governed runtime.

`PinnedLocalVadAdapter` and `PinnedLocalSttAdapter` are the in-memory adapter boundary. They require a validated runtime-artifact seal and the same deployment manifest as the audio data plane. VAD returns only probability/hash lineage and deliberately leaves audio buffered for STT. STT returns transient text to the caller while its provenance/audit identity is the text SHA-256; raw transcript text is not part of the sealed execution fingerprint.

## Concrete native VAD and STT engines

`voice_native_engines.py` implements the first real local input execution path rather than only Protocol interfaces.

- `SileroOnnxVadEngine` re-hashes the exact ONNX model before session construction, requires the expected `input/state/sr` contract, uses CPU ONNX Runtime locally and passes PCM directly from RAM. EAY uses exact 512-sample windows at 16 kHz. Recurrent state/context are recreated per governed score call so raw utterance context is not retained across callbacks.
- `WhisperCppSttEngine` passes PCM16 directly in memory to an EAY-owned stable C ABI shim. The shim uses whisper.cpp's public PCM API rather than creating a temporary WAV file. The exact model and exact shim shared-library bytes are re-hashed before execution.
- `native/eay_whisper_shim.cpp` must be built with whisper.cpp statically linked into the attested shared-library artifact. A separately drifting dynamic libwhisper is not an eligible production build because its bytes would not be covered by the runtime seal.
- The optional `voice-onnx` dependency group contains NumPy + ONNX Runtime for the concrete Silero path. Production still requires exact downloaded model hashes, promotion evidence and runtime attestation; installing an optional dependency alone grants no production eligibility.

`VoiceLocalInputPipeline` composes the RAM data plane, frame-by-frame `VoiceInputLineageTracker`, pinned VAD, pinned STT and transient transcript handling. It requires speech to have been detected before finalization, consumes/wipes all utterance PCM through STT, and returns a hash-only end-to-end utterance proof binding wake proof, microphone chain, VAD result, STT result, STT runtime seal and text SHA-256.

## Per-language TTS artifact and resource lineage

`voice_tts_bundle.py` treats TTS as more than a runtime executable. Every TR/EN/DE/AR/FA voice entry pins its own model, config, `tokens.txt`, model card and artifact-license identity. The bundle separately pins the shared phonemizer-data directory manifest, its license ID and its authoritative source. Human bundle promotion seals the exact aggregate fingerprint, so changing one language's model/tokens/config/model-card or any shared phonemizer resource creates a new unpromoted bundle.

The deployment manifest seals that promoted TTS bundle identity alongside the promoted TTS runtime. `tts_start` derives the active language artifact only from the server-side session language. A client cannot override model, config, tokens, model-card, phonemizer manifest/license/source or bundle fingerprints. The resulting `VoiceTtsGenerationProof` is self-validating: changing one field without resealing the entire proof is rejected as fingerprint drift.

## RAM-only TTS output

`voice_tts_native_engine.py` provides a governed whole-utterance sherpa-onnx VITS/Piper path using `OfflineTts.generate()`. Before construction it verifies the exact language model, config, tokens and model-card files, reconstructs the deterministic phonemizer resource manifest, and checks runtime promotion/deployment lineage. It consumes generated samples directly from memory and creates an EAY-owned PCM16 buffer without creating a WAV file.

The whole-utterance path remains useful as a compatibility/fallback boundary, but it cannot interrupt native compute while `OfflineTts.generate()` itself is blocked. EAY therefore does not use this path as evidence that the first-audio or barge-in release targets are satisfied.

## Interruptible native TTS streaming

`native/eay_sherpa_tts_shim.cpp` and `voice_tts_streaming_engine.py` add the preferred interruptible path. The EAY C ABI wraps sherpa-onnx's current `SherpaOnnxOfflineTtsGenerateWithConfig()` progress-callback API rather than the older deprecated callback entry points. The upstream callback contract returns `1` to continue and `0` to stop early; EAY maps cancellation or a downstream consumer stop directly to that native return value so generation can be interrupted during the callback loop instead of merely discarding a completed waveform.

The shim constructs a VITS configuration only from pinned model/tokens/phonemizer paths, uses the CPU provider, queries the engine's output sample rate and immediately destroys sherpa's aggregate generated-audio object after callback generation. The production shim must be statically linked with the reviewed sherpa-onnx build, or every dynamic native dependency must be separately attested; hashing an EAY shim that dynamically loads unpinned libraries is insufficient.

The Python streaming engine re-verifies model/config/tokens/model-card files and the complete phonemizer directory before native context creation. Each callback chunk is copied immediately into an EAY-owned PCM16 `bytearray`, synchronously passed to the consumer, chained into a SHA-256 audio lineage and then zeroized before native generation continues. Completed synthesis returns hash-only lineage plus sample count, first-audio latency, total generation time, audio duration and real-time factor. Cancellation or consumer stop returns a failed/cancelled generation rather than a partial result eligible for normal response completion.

The current CI validates the EAY streaming state machine and cancellation propagation with an injected shim, and statically verifies that the native source uses the current `GenerateWithConfig` API. CI does not yet build or benchmark a real sherpa-onnx shared library or real voice models. Therefore no production latency/naturalness claim is made until a reproducible native build plus actual TR/EN/DE/AR/FA measurement evidence exists.

## Immutable multilingual release evidence

`voice_release_gate.py` keeps the release thresholds fail closed and now validates the measurement domain itself. NaN/infinite scores, negative latency/count values and out-of-range rate/naturalness values are rejected before threshold evaluation. The existing production thresholds remain: at least 50 samples per core language; STT WER <= 0.12; semantic consistency >= 0.98; naturalness 4.0–5.0; citation readback >= 0.995; p95 first audio <= 900 ms; p95 barge-in <= 300 ms; interruption success >= 0.995; p95 cancellation propagation <= 250 ms; and zero accepted approval replays.

`voice_release_evidence.py` makes those metrics auditable rather than accepting free-floating numbers. Each language record binds its sealed metric fingerprint to the exact deployment manifest, model execution identity, TTS bundle execution identity, full runtime-attestation bundle, eval-suite hash, measurement-harness hash, runtime-environment fingerprint, raw-measurement manifest hash, human-review manifest hash, reviewer, approval reference and timestamp. Only hashes/metrics are stored; raw microphone audio, generated PCM, transcripts and human review text are not inserted into this registry.

A governed release decision requires exactly one immutable record for each TR/EN/DE/AR/FA language. Cross-deployment/model/TTS/runtime-attestation/eval-suite/harness mixtures fail closed. Failed metric sets are still sealed for audit, but `require_release()` refuses to authorize them as production-ready.

## Production session bootstrap

`configure_verified_voice_deployment()` remains a staging/evaluation path: it verifies current model, adapter and TTS promotions but deliberately does not mark the binding production-released. `configure_released_voice_deployment()` is the production path. It first rebuilds the exact current registry-backed deployment without changing global runtime state, verifies the full runtime-attestation bundle against that deployment, requires an approved governed release decision with exact model/TTS/runtime fingerprints, and only then installs the server binding. A failed release check therefore never leaves a partially installed global binding.

`EAY_VOICE_RUNTIME_MODE` defaults to `production`. In production mode the WebSocket refuses to accept a session unless the installed binding carries the governed release-decision fingerprint and runtime-attestation-bundle fingerprint. Evaluation/development/test modes must be selected explicitly for non-production use. During a session, freshness checks also pin the release-decision and runtime-attestation fingerprints in addition to the deployment manifest, so a silent release/runtime lineage swap blocks later turns/results.

## Privacy-preserving session audit

`VoiceSessionLedger` creates an append-only SHA-256 chain for wake, utterance, tool, approval, response and interruption events. It rejects raw-audio/transcript metadata and requires tool-call IDs and explicit approval references where applicable. TTS proof audit metadata includes the exact language model/config/tokens/model-card lineage plus shared phonemizer manifest/license/source hashes. This provides incident/audit lineage without silently creating a raw voice recording store.

## Current runtime state

The governed runtime now includes WebSocket sequencing/replay protection, bounded conversation memory, full-duplex/barge-in cancellation, single-use approval tokens, tool execution provenance, deployment/release freshness checks, model/TTS response lineage, microphone-to-STT hash lineage, a bounded RAM-only PCM input data plane, exact runtime-binary and resource-directory attestation, concrete Silero ONNX VAD, an in-memory whisper.cpp C-ABI STT path, an end-to-end local microphone/VAD/STT coordinator, promoted per-language TTS bundle lineage, a fileless whole-utterance sherpa-onnx TTS boundary, an interruptible EAY C-ABI callback streaming boundary, a four-adapter runtime-attestation bundle and immutable five-language release evidence enforced by production session bootstrap.

No TTS bundle or native model is auto-downloaded or automatically production-promoted. The architecture can now represent and enforce production evidence, but the repository still does not contain actual approved TR/EN/DE/AR/FA voice artifacts, a reproducibly built sherpa-onnx production shim, or real measured release records. The next implementation layer is a reproducible measurement harness/native build pipeline that emits the raw-measurement manifests consumed by `voice_release_evidence.py`; only real hardware/runtime measurements and human naturalness review can turn those gates into an approved production release.
