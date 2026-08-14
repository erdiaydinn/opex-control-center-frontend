# EAY AI Training — Governed Local Training and Production Acceptance

## Purpose

This runbook is the canonical operator path from reviewed learning evidence to a locally trained LoRA/QLoRA artifact and, only after all evidence gates pass, to model production promotion.

Repository readiness is not production acceptance. A real training acceptance run still requires approved production-quality train/eval data, an approved local base model artifact, suitable physical CPU/GPU hardware, and an observed training run. Synthetic fixtures and CI contract backends never count as that evidence.

## Non-negotiable gates

1. Only reviewed learning examples may enter the dataset.
2. Personal-data/privacy, teacher-quality, multilingual and training-quality gates must pass.
3. Train and eval splits must be distinct and leakage checks must pass.
4. The dataset manifest, training job and execution plan are immutable and hash-bound.
5. Base model, train data and eval data are re-hashed from disk immediately before execution.
6. Training is local-only. Remote code and model/dataset network fetches are disabled.
7. QLoRA requires CUDA and uses the reviewed 4-bit NF4 configuration.
8. The actual output tree is hashed after training. Runtime evidence is stored inside that tree before the receipt hash is created.
9. Artifact drift after receipt creation invalidates the receipt.
10. Legacy `ModelRegistry.promote()` is fail-closed. Production mutation is only through `ModelPromotionGate`.
11. The public promotion POST is disabled unless deployment-authoritative operator identity and a strong bearer secret are configured.
12. Production promotion still requires artifact provenance, offline/release eval evidence, passing canary evidence and the verified training execution receipt.

## Environment

From `services/eay-ai-core`:

```bash
python -m pip install -e '.[dev]'
```

On the real local training worker:

```bash
python -m pip install -e '.[training]'
```

The executor sets the reviewed offline flags before loading training libraries:

```text
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_DATASETS_OFFLINE=1
WANDB_DISABLED=true
TOKENIZERS_PARALLELISM=false
```

The base model must already exist on local disk. The training executor uses `local_files_only=True` and `trust_remote_code=False`.

## 1. Produce reviewed train/eval JSON

The public learning export at `/v1/learning/export` is gated. There is no raw approved-candidate export shortcut on the production surface.

Persist the reviewed train and eval arrays as JSON files. Each example must retain the reviewed metadata required by the training/teacher/privacy gates.

Example paths used below:

```text
./evidence/train.json
./evidence/eval.json
./models/reviewed-base/
./artifacts/eay-adapter-v1/
./data/eay_ai.db
```

## 2. Create the immutable dataset manifest

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  create-manifest \
  --train-json ./evidence/train.json \
  --eval-json ./evidence/eval.json \
  --approved-by DATASET_REVIEWER_ID \
  --approval-reference DATASET-REVIEW-2026-001
```

Record at minimum:

- `dataset_sha256`
- `eval_dataset_sha256`
- `dataset_integrity_sha256`
- `quality_lineage_sha256`
- `chain_sha256`
- manifest `id`

If this command fails, do not bypass the gate or edit the stored hashes.

## 3. Prepare and register the training job

Create `job-spec.json` with the exact reviewed manifest hashes and base-model tree hash. The supported execution methods are `lora` and `qlora`.

The spec must remain:

```json
{
  "local_only": true,
  "allow_remote_code": false,
  "allow_network_during_training": false
}
```

Register it:

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  register-job \
  --spec-json ./evidence/job-spec.json \
  --approved-by TRAINING_REVIEWER_ID \
  --approval-reference TRAINING-JOB-2026-001
```

Record the returned `fingerprint`.

## 4. Create the immutable execution plan

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  create-plan \
  --training-job-fingerprint JOB_FINGERPRINT \
  --base-model-path ./models/reviewed-base \
  --training-dataset-path ./evidence/train.json \
  --eval-dataset-path ./evidence/eval.json \
  --output-path ./artifacts/eay-adapter-v1 \
  --requested-by TRAINING_OPERATOR_ID \
  --execution-reference LOCAL-TRAIN-2026-001
```

The plan re-hashes all three inputs. A changed base model or changed dataset must fail here.

## 5. Mandatory dry-run preflight

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  preview \
  --plan-fingerprint PLAN_FINGERPRINT
```

Do not execute unless the preview confirms:

- expected `training_job_fingerprint`
- expected method
- expected base/train/eval hashes
- `local_only=true`
- `allow_remote_code=false`
- `allow_network_during_training=false`
- offline environment flags enabled

## 6. Run the real local training job

On the approved physical training worker:

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  execute \
  --plan-fingerprint PLAN_FINGERPRINT \
  --executor PHYSICAL_WORKER_ID \
  --execution-reference LOCAL-TRAIN-2026-001:EXIT-0
```

For LoRA the executor uses the reviewed PEFT/SFT settings from the immutable job. For QLoRA it additionally requires CUDA and uses 4-bit NF4 with double quantization.

A successful run writes `eay_training_runtime_evidence.json` inside the output directory before the artifact-tree receipt is created. The receipt therefore binds runtime evidence together with the trained adapter files.

This step is a **field/hardware acceptance gate**. CI fake backends do not satisfy it.

## 7. Re-verify the observed artifact receipt

```bash
python -m app.training_operator_cli \
  --db-path ./data/eay_ai.db \
  verify-receipt \
  --training-job-fingerprint JOB_FINGERPRINT \
  --artifact-sha256 ARTIFACT_SHA256
```

The command re-hashes the live artifact tree. Any post-training change must invalidate the receipt.

## 8. Register artifact provenance and model candidate

Use the existing model artifact/provenance and model registry flows. The candidate must remain non-production while offline eval, safety/legal/RAG eval and canary evidence are incomplete.

The artifact SHA used here must be exactly the SHA from the verified training execution receipt.

## 9. Run offline, safety, RAG and historical legal evaluations

Production promotion must not rely only on a generic quality score. Preserve the exact release-evaluation and historical/safety evidence fingerprints required by `ModelPromotionGate`.

If any stored offline-eval fingerprint or current model state drifts after review, promotion is rejected.

## 10. Run controlled canary acceptance

The canary evidence must be artifact-bound and passing. A CI/synthetic canary proves contract behavior only; production acceptance requires the actual target model/artifact and approved target environment.

## 11. Configure release authority only at deployment

The POST production-promotion API is disabled by default. Configure both values through the deployment secret/identity mechanism, never source control:

```text
EAY_MODEL_PROMOTION_OPERATOR_ID=<deployment-authoritative release operator identity>
EAY_MODEL_PROMOTION_API_TOKEN=<strong secret, minimum 32 characters>
```

A caller cannot choose `approved_by`; it is derived from `EAY_MODEL_PROMOTION_OPERATOR_ID`.

This repository-level bearer boundary prevents an unauthenticated production mutation. It does **not** replace future corporate OIDC/SSO identity evidence where that is required by the deployment environment.

## 12. Perform governed production promotion

`POST /v1/model-promotions` requires:

```http
Authorization: Bearer <deployment secret>
```

Request body contains only:

```json
{
  "model_record_id": "...",
  "canary_evidence_fingerprint": "<64-hex>",
  "release_evaluation_evidence_fingerprint": "<64-hex>",
  "approval_reference": "RELEASE-2026-001"
}
```

The server derives the release operator identity. The canonical gate then re-verifies the model, training job, actual execution receipt, artifact provenance, eval evidence, canary evidence and current database state atomically before creating the immutable production proof.

`GET /v1/model-promotions/{model_record_id}` re-verifies the current production proof rather than merely returning stale stored metadata.

## Acceptance evidence to retain

For every real candidate retain:

- dataset manifest ID and chain SHA
- exact train/eval dataset SHA values
- base model SHA and license decision
- training-job fingerprint
- execution-plan fingerprint
- physical worker identity and execution reference
- `eay_training_runtime_evidence.json`
- execution-receipt fingerprint
- artifact SHA
- artifact provenance fingerprint
- offline/release/safety/RAG/legal eval fingerprints
- canary evidence fingerprint
- release approver identity/reference
- final production release-proof fingerprint

## Repository-complete vs field-complete

Repository completion means all gates, CLI paths, tests, fail-closed policies, evidence bindings and release topology are green. It does not mean a model was genuinely trained or accepted on production hardware/data.

The remaining field acceptance after repository completion is deliberately narrow:

1. approved production-quality train/eval corpus,
2. reviewed local base-model artifact and license evidence,
3. real physical training worker/GPU execution,
4. observed resource/runtime behavior,
5. real artifact-bound offline/canary evaluation,
6. deployment-authoritative release identity/secret provisioning,
7. controlled production canary and release acceptance.

Never replace any of those with synthetic CI evidence.
