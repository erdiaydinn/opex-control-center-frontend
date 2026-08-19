# EAY Audit Visual Model Admission v1

Status: architecture / admission policy; not field acceptance evidence.

## Product rule

EAY Audit does not send every photo/video frame to one large multimodal model. The governed path is:

`capture -> privacy redaction -> scene/step sampling -> deterministic CV/OCR -> standard rule -> local VLM only when semantic interpretation is needed -> human review when evidence/confidence is insufficient`

Paid frontier inference remains an exception governed by the existing EAY model-routing and grant policy.

## Candidate stack

| Capability | Preferred candidate family | Intended use | Admission posture |
|---|---|---|---|
| Face privacy | Google MediaPipe Tasks Vision | local face detection before any audit inference | admit only with exact model SHA-256, byte count, provenance and license receipt |
| Video segmentation / tracking | Meta SAM 2 | selected object masks/tracks across sampled video spans | candidate; benchmark device/server cost and domain accuracy |
| Open-vocabulary grounding | Grounding DINO | locate standard-described objects such as extinguisher, exit, pallet, oven, shelf | candidate; pair with deterministic standard vocabulary |
| Real-time object detection | RT-DETR family from Paddle ecosystem | fixed retail/warehouse classes when a trained detector is superior to VLM inference | candidate; prefer reviewed permissive-license implementation/model |
| OCR | PaddleOCR | labels, dates, signage and structured text where evidence contract permits OCR | candidate; privacy filtering still precedes downstream persistence |
| Semantic vision/video reasoning | Qwen3-VL family | ambiguous scene relation/attribute interpretation after deterministic filtering | local specialist candidate; not authoritative arithmetic or policy source |

## Non-default candidates

Ultralytics packages/models are not a default EAY Audit dependency. Their current open-source/commercial licensing model requires explicit commercial/legal admission before use in a proprietary product. EAY should not silently introduce AGPL or commercial-license obligations into the platform.

## Evidence contract controls model use

Each Audit question/control must declare:

- evidence modality: PHOTO / VIDEO / OCR / SYSTEM_DATA / SENSOR / HUMAN_ATTESTATION or combination;
- observable target(s) and forbidden/required state;
- required views / minimum evidence quality;
- deterministic rule if available;
- detector/segmenter/OCR/VLM capability class allowed;
- minimum confidence/calibration policy;
- REVIEW_REQUIRED / INSUFFICIENT_EVIDENCE behavior;
- risk class and whether human confirmation is mandatory;
- closure evidence contract.

A model is never allowed to transform an unobservable control into PASS. For example, training completion, actual refrigerator temperature or inventory-system truth require their authoritative system/sensor sources even if a photo exists.

## Video economics

Video analysis is event/key-frame driven. Candidate frames may be dropped before canonical evidence admission. A frame becomes canonical only after:

1. capture-step association;
2. sampling policy acceptance;
3. privacy redaction;
4. fingerprinted private evidence persistence;
5. server-issued storage receipt;
6. server privacy verification.

Only then may governed visual inference consume the evidence.

## Benchmark before field authority

Per control class, benchmark against labeled field evidence across stores, devices, lighting, occlusion and camera motion. Track at minimum precision, recall/sensitivity, false-critical rate, calibration, human override rate, insufficient-evidence rate and closure re-verification error. Critical safety controls require a stricter acceptance policy and human confirmation until field evidence demonstrates otherwise.

## Truth boundary

Repository presence, successful compilation or a model license alone is not field proof. No candidate above is production-authoritative for EAY Audit until the exact model artifact, license/provenance, benchmark dataset, evaluation receipt and rollout decision are versioned and approved.
