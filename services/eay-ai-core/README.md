# EAY AI Core v0.1

Local-first, regulatory-aware Food & Retail Operations Intelligence service.

This is the first runnable EAY language-model layer. It deliberately separates:

- **LEGAL** — binding legislation/regulatory evidence.
- **COMPANY** — internal company SOPs and standards.
- **STANDARD** — voluntary/sector standards and best practices.
- **OPERATIONAL** — live/historical operational facts.
- **LEARNING** — corrections, uncertain answers, teacher review, and approved SFT examples.

## Why this architecture

Current law and company policy must **not** be baked permanently into model weights. They change.

The model learns stable capabilities such as food/retail reasoning, root-cause analysis, tool use, company-vs-law separation, source discipline and risk reasoning. Changing facts remain in a versioned knowledge layer and are retrieved for the requested `as_of` date.

## v0.1 guarantees

- No paid LLM API is required.
- Ollama runs the student model locally.
- SQLite + FTS5 provides a zero-paid-token retrieval layer.
- Legal claims are downgraded to `insufficient` when no binding legal evidence was retrieved.
- Model citations are filtered against retrieved evidence IDs.
- Low-confidence answers and user corrections enter a learning queue.
- A larger **local** Ollama model can optionally act as the teacher.
- Only approved learning candidates are exported as future fine-tuning examples.
- The service never auto-deploys new model weights.

## Architecture

```text
OPEX / Audit / Academy / Other Clients
                |
                v
           EAY AI Core
                |
       +--------+---------+
       |                  |
Knowledge Layers      Learning Loop
       |                  |
SQLite/FTS5          feedback/low confidence
       |                  |
       v                  v
  Local Ollama       local teacher model
       |                  |
       +---------+--------+
                 |
          approved SFT data
                 |
        future LoRA/QLoRA job
```

Qdrant, Graphiti, regulatory watchers, vision audit, Langfuse and Superset are later adapters. The v0.1 core stays intentionally small.

## Windows quick start

Requirements:
- Python 3.11+
- Ollama

PowerShell:

```powershell
cd services\eay-ai-core
Set-ExecutionPolicy -Scope Process Bypass -Force
.\START_EAY_AI.ps1
```

The script creates the Python environment, installs dependencies, pulls the local base model when needed, creates `eay-ops:0.1`, and starts the API.

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
```

Swagger:

`http://127.0.0.1:8010/docs`

## Add knowledge

Example company rule:

```json
{
  "id": "company-demo-001",
  "layer": "company",
  "title": "Demo Internal Standard",
  "content": "Example only. Replace with an approved company SOP.",
  "source_name": "Approved Company SOP",
  "jurisdiction": "TR",
  "authority_level": "company",
  "effective_from": "2026-01-01",
  "version": "1.0"
}
```

Send it to `POST /v1/knowledge`.

### Legal documents

For `layer=legal`:

- use only authoritative sources,
- store the real source URL,
- store effective dates,
- use `authority_level=binding` only when the source is actually binding,
- preserve old versions so historical `as_of` questions remain answerable.

Do not seed legal text from blogs or model memory.

## Ask a question

`POST /v1/chat`

```json
{
  "message": "Bu uygulama şirket standardına ve mevzuata uygun mu?",
  "as_of": "2026-08-10",
  "company": "Example Company",
  "layers": ["legal", "company", "standard", "operational"]
}
```

The response keeps legal/company/standard/operational findings separate and returns the exact evidence used.

## Learning loop

Give feedback with `POST /v1/feedback`:

```json
{
  "interaction_id": "<returned interaction id>",
  "rating": 1,
  "corrected_answer": "Approved corrected answer",
  "reason": "Company rule was interpreted incorrectly"
}
```

Review queue:

`GET /v1/learning/candidates`

Optional local teacher: set `EAY_TEACHER_MODEL` in `.env` to a larger local Ollama model, then call:

`POST /v1/learning/candidates/{candidate_id}/teacher-review`

Human approves or rejects:

- `POST /v1/learning/candidates/{candidate_id}/approve`
- `POST /v1/learning/candidates/{candidate_id}/reject`

Export approved SFT dataset:

`GET /v1/learning/export`

This output becomes the controlled input for the future LoRA/QLoRA training pipeline.

## Next implementation layers

1. Official Turkish regulatory watcher with source/version diffing.
2. Qdrant hybrid retrieval and Graphiti temporal knowledge.
3. Company document ingestion with Docling/PaddleOCR.
4. BigQuery/tool connectors with scoped permissions.
5. Vision audit service: OpenCV + detection + Anomalib + SAM2 + OCR.
6. Langfuse traces/evals and Promptfoo regression gates.
7. Superset embedded analytics.
8. LoRA/QLoRA training job + model registry + canary rollout.

## Safety rule

**EAY can identify learning opportunities, but EAY cannot directly replace its own production weights.**

Training candidates require evidence, evaluation and explicit approval before a new model version is promoted.
