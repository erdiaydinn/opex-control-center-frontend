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
- Regulatory source monitoring uses an allow-listed official-source registry; arbitrary URLs are not accepted.
- Detected website changes are never auto-promoted to binding legal knowledge.
- Operational KPI execution is allowed only when both a reviewed business-semantic contract and a reviewed live-schema contract pass. Their SHA-256 fingerprints are stored with the execution audit.

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

Official Turkish Sources
        |
        v
 Regulatory Watcher
        |
 baseline -> hash -> diff -> relevance filter
        |
        v
 pending regulatory change
        |
 exact legal text + effective-date verification
        |
        v
      LEGAL layer
```

Qdrant, Graphiti, document ingestion, vision audit, Langfuse and Superset are later adapters. The v0.1 core stays intentionally small.

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

## Regulatory Watcher v0.1

The source registry is stored at:

`config/regulatory_sources.json`

Initial official Turkish sources:

- T.C. Tarım ve Orman Bakanlığı / GKGM home and announcements — discovery.
- Gıda Kodeks ve Yem Mevzuatı Daire Başkanlığı — official registry/guidance discovery.
- KAYSİS GKGM legislation registry — official registry.
- T.C. Resmî Gazete — binding-publication index.
- Tarım ve Orman Bakanlığı Güvenilir Gıda — official guidance/discovery.

List configured sources:

`GET /v1/regulatory/sources`

Create the first baseline or check for changes:

`POST /v1/regulatory/check`

Check one source:

`POST /v1/regulatory/check?source_id=tr-gkgm-kodeks`

Pending changes:

`GET /v1/regulatory/changes?status=pending`

Acknowledge/reject a signal:

- `POST /v1/regulatory/changes/{change_id}/acknowledge`
- `POST /v1/regulatory/changes/{change_id}/reject`

**Important:** acknowledgement means “this change was reviewed as a signal.” It does **not** mean that the changed web page has become a binding legal source. Promotion to `LEGAL / binding` requires the exact legal instrument, publication/source verification and effective dates.

The watcher intentionally checks official government sources sequentially rather than aggressively scraping them in parallel.

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

## CI quality gate

`.github/workflows/eay-ai-core-ci.yml` compiles and tests EAY AI Core on relevant branch/PR changes.

The goal is that autonomous development remains constrained by a repeatable test gate rather than relying only on model-generated code review.

## Next implementation layers

1. Exact legal-instrument ingestion + effective-date/version extraction and regulatory impact classification.
2. Company-vs-law conflict engine with stricter/looser/incompatible classification.
3. Qdrant hybrid retrieval and Graphiti temporal knowledge.
4. Company document ingestion with Docling/PaddleOCR.
5. BigQuery/tool connectors with scoped permissions and dual semantic/schema KPI contracts.
6. Vision audit service: OpenCV + detection + Anomalib + SAM2 + OCR.
7. Langfuse traces/evals and Promptfoo regression gates.
8. Superset embedded analytics.
9. LoRA/QLoRA training job + model registry + canary rollout.

## Safety rule

**EAY can identify learning opportunities, but EAY cannot directly replace its own production weights.**

Training candidates require evidence, evaluation and explicit approval before a new model version is promoted.
