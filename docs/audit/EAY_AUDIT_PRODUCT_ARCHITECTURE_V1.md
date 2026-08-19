# EAY Audit Product Architecture V1

## Product position

EAY Audit is not a digital checklist clone. It is the audit operating system for EAY: standards, evidence, visual/video intelligence, corrective action, assurance, reporting and Jarvis intelligence share one governed model.

Audit Now is treated as a minimum usability benchmark, not the target. The product must also compete with the mature workflow patterns visible in SafetyCulture and GoAudits: inspection-to-action linkage, cross-site analytics, recurring findings and web/mobile role separation.

## Non-negotiable product rules

1. **Web and mobile are separate experiences.** Web is a management/analysis/configuration command center. Mobile is a field capture/execution surface. Responsive reuse is allowed at component level; shrinking the desktop workspace into the app is not.
2. **No synthetic business truth.** Empty/unbound states remain empty until real audits or authorized company sources exist.
3. **Privacy before inference.** Photo/video cannot enter visual reasoning until a redaction receipt proves face/PII anonymization. Face recognition is forbidden.
4. **AI confidence is not audit truth.** A decision keeps source, time, location, model/rule and human disposition together.
5. **Completed is not closed.** Corrective action requires fresh closure evidence plus AI or authorized human verification.
6. **AI–auditor disagreement is a quality signal.** Disagreement routes to the auditor manager; manager-backed override escalates to Operations Standards and contributes to auditor/model calibration.
7. **Deterministic when possible, local AI when necessary, frontier only by exception.** Standard checks and action templates should not consume paid model tokens when deterministic rules are sufficient.
8. **Store DNA controls applicability.** Asset/location facts determine which standards apply; absent equipment can become governed N/A rather than forcing a fabricated answer.

## Web experience

Primary surfaces:

- Audit Command Center
- Audits / Results
- Standards Studio
- Scheduling
- Actions: Table / Kanban / Calendar / **Intelligence View**
- Locations & Store DNA
- Assurance / AI–Auditor Calibration
- Analytics
- Jarvis Audit Intelligence
- Notification / escalation settings
- Report/PDF configuration

The web foundation intentionally renders live KPI values as `—` while the audit truth source is unbound.

## Mobile experience

The mobile app is capture-first:

- Home / assigned audits / actions
- one-tap `Video Audit`
- guided capture stages such as entrance, coffee, oven, shelves and cold zone
- live privacy-redaction state
- evidence quality/progress
- offline queue and sync status
- action closure capture
- reviewer feedback where the user's role permits it

The field user does not need to see every audit question. Guided capture can collect enough evidence for the standards engine to answer eligible checks in the background; insufficient evidence remains `REVIEW_REQUIRED` or `INSUFFICIENT_EVIDENCE`.

## Media and privacy pipeline

```text
Camera / Upload
  -> device-scoped raw buffer
  -> face/PII detection
  -> blur / pixelation / masking
  -> RedactionReceipt
  -> scene/key-frame selection
  -> object detection / segmentation / tracking / OCR
  -> local VLM or video model when needed
  -> deterministic standards engine
  -> finding + evidence receipt
  -> action / assurance / report
```

Raw identifiable media is not the default audit evidence object. Redacted derivatives are the governed evidence surface. Temporary anonymous person-track identifiers may be used during one processing session, but they must not become biometric identity.

## Technology research and adoption map

### Android capture

Use Jetpack CameraX as the native capture foundation. Official Android documentation supports Preview, ImageAnalysis, ImageCapture and VideoCapture combinations, and CameraX's Compose integration is intended for adaptive camera experiences. This matches EAY's requirement for a purpose-built native field app rather than a web wrapper.

### Local privacy preprocessing

Evaluate Google MediaPipe Tasks Vision for face detection/redaction preprocessing. MediaPipe supports image, video and live-stream modes and is Apache-2.0 at repository level. The EAY privacy adapter must expose only bounding regions/redaction receipts to later stages; no identity recognition is needed.

### Video scene/object intelligence

Candidates retained for governed evaluation:

- `facebookresearch/sam2` — image/video segmentation, Apache-2.0.
- `IDEA-Research/GroundingDINO` — open-set text-grounded object detection, Apache-2.0.
- `IDEA-Research/Grounded-SAM-2` — grounding and tracking in video with Grounding DINO / Florence-2 / SAM 2, Apache-2.0.
- `QwenLM/Qwen3-VL` — multimodal model with video examples/evaluation, Apache-2.0 repository license.
- `OpenGVLab/InternVideo` — video foundation / multimodal understanding, Apache-2.0.
- `open-mmlab/mmaction2` — action recognition and temporal localization, Apache-2.0.
- `Breakthrough/PySceneDetect` — scene/transition detection, BSD-3-Clause.
- `roboflow/supervision` — reusable detection/tracking/video utilities, MIT.
- `PaddlePaddle/PaddleOCR` — OCR/document extraction, Apache-2.0.
- `open-compass/VLMEvalKit` — multimodal evaluation harness, Apache-2.0.

`ultralytics/ultralytics` is not a default embedded dependency because its public repository is AGPL-3.0; commercial adoption requires an explicit license decision.

Every third-party component must enter through Repository Intelligence with exact upstream, pinned commit/tag, license review, security review and benchmark/evaluation evidence. Discovery is not admission.

## Standards contract

Each question/standard should evolve toward:

```text
standard_id
version
effective_from
category
subcategory
question
info_for_auditor
expected_answer
failure_condition
score_weight
applicability_rule
evidence_contract
vision_contract
default_risk_class
priority_policy
sla_policy
action_template
owner_rule
escalation_rule
mail_routing_rule
closure_evidence_contract
```

Existing company question/setup files should be imported without silently rewriting their content. Conflicts in scoring or historical rule changes must be versioned, not overwritten.

## Assurance workflow

```text
AI decision
  -> auditor decision
     -> aligned: persist outcome
     -> disagreement: MANAGER_REVIEW
        -> manager sides with AI: resolve + auditor calibration signal
        -> manager sides with auditor: OPERATIONS_STANDARDS_REVIEW
           -> standard/model/human calibration decision
```

Reporting should expose disagreement rate, validated override rate and repeated disagreement clusters without turning them into automatic HR sanctions.

## Action lifecycle

```text
OPEN
 -> IN_PROGRESS
 -> SUBMITTED_FOR_VERIFICATION
 -> AI_VERIFIED | HUMAN_VERIFIED
 -> CLOSED
```

A failed verification returns to an actionable state. SLA policy is not just Critical/High/Medium/Low; risk domain matters (life safety, food safety, legal, operational, brand, etc.).

## Jarvis Audit Intelligence

Jarvis should answer evidence-bound questions such as:

- Which locations deteriorated this month and why?
- Which findings repeat after closure?
- Where do AI and auditors disagree most?
- Which managers have high overdue-action concentration?
- Which finding clusters correlate with inventory/workforce/planogram/operations signals?
- Create the executive PDF and route it to the governed recipients.

Metrics/calculations come from deterministic semantic/query layers. Jarvis interprets, compares hypotheses, asks for missing evidence and generates grounded narrative; it does not invent KPI values.

## Current V1 code boundaries

Web V1 adds `/audit`, a localized Audit Command Center, explicit unbound live-truth state, privacy/evidence/action/assurance contracts and a product-state test gate.

Android V1 adds a separate native mobile audit shell plus a fail-closed privacy receipt contract. The CameraX capture engine and concrete MediaPipe redaction implementation are intentionally the next slice, so the UI/contract can be CI-validated before adding device/model dependencies.

## Next acceptance slices

1. Exact-head web CI/build and Android unit/compile gates GREEN.
2. CameraX guided capture surface and offline-safe media queue.
3. Concrete on-device face redaction adapter with adversarial tests: multiple faces, partial face, motion blur, rotation, occlusion, frame drops and redaction failure.
4. Scene/key-frame pipeline and evidence quality scoring.
5. Standards import/versioning and Store DNA applicability.
6. Audit execution/result/action persistence through authoritative Core APIs.
7. PDF/mail routing and WORM evidence trail.
8. Jarvis semantic layer + disagreement/recurrence analytics.
9. Field benchmark against labeled company audit photos/videos before any auto-finding production authority.
