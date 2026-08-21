# EAY Academy multilingual Learning OS contract

## Truth boundary

EAY uses two language-support tiers and they must never be conflated.

### UI release tier

The complete product UI release contract remains:

`tr`, `en`, `de`, `ar`, `fr`, `es`, `it`, `nl`, `pl`, `pt-BR`.

These languages require critical translation-key completeness, interaction QA and accessibility acceptance before EAY may claim that the application UI is production-ready in the language. `Accept-Language` negotiation remains limited to this tier.

### Academy content and evidence tier

Academy, SOP/document evidence, quizzes, captions, transcripts and grounded knowledge can additionally use:

`fa`, `ru`, `ro`, `bs-Latn`, `sq`, `ka`, `ku-Latn`, `ckb`, `bg`, `hy`, `zh-Hans`, `sr-Latn`, `mk`, `id`, `hu`, `az`, `uk`, `el`, `ms`, `uz-Latn`, `hi`, `ur`, `pt-PT`, `ja`, `ko`, `cs`, `sk`, `sv`, `da`, `no`, `fi`, `he`, `th`, `vi`, `bn`, `ps`.

A content locale does not imply that the full EAY UI is translated into that language.

## Canonicalization

Existing compact values such as `tr`, `en`, `de` and `ar` remain valid. Common BCP-47/regional forms are normalized at the API boundary, for example:

- `tr-TR` -> `tr`
- `en-US` -> `en`
- `fa-IR` -> `fa`
- `ur-PK` -> `ur`
- `ckb-IQ` -> `ckb`
- `ku-Latn-TR` -> `ku-Latn`
- `zh-CN` -> `zh-Hans`
- `pt_BR` -> `pt-BR`

Script-sensitive languages use explicit mappings rather than guessing from ambiguous tags. If two submitted i18n keys normalize to the same canonical locale, Academy rejects the request instead of silently overwriting one translation.

## RTL

UI release RTL currently covers Arabic because Arabic is the RTL language in the verified UI release tier. Academy content/evidence RTL additionally declares:

- Arabic (`ar`)
- Persian (`fa`)
- Urdu (`ur`)
- Sorani Kurdish (`ckb`)
- Hebrew (`he`)
- Pashto (`ps`)

This is direction metadata, not a visual/accessibility acceptance claim. Every RTL language still needs staging layout, keyboard/focus, screen-reader, captions/transcript and typography QA before field release.

## Grounded knowledge and translation safety

Academy RAG is exact-locale by default. A Persian question does not silently retrieve a Turkish or English SOP and present it as Persian policy evidence. If a translated policy is published, it must remain linked to the exact authoritative content version and retain source/version provenance.

Machine translation may assist authoring, but a machine-generated SOP/policy translation is not authoritative merely because it exists. Published policy translations require tenant-controlled review/approval evidence.

## Persistence and disaster recovery

Migration `0045_academy_content_locale_expansion` widens Academy content-version and document-chunk locale storage to `varchar(16)` and replaces the original TR/EN/DE/AR database checks with the content/evidence catalog. The downgrade refuses to run while expanded-locale rows exist, preventing truncation or silent data loss.

Academy convergence DR acceptance seeds a Persian published content version and Persian document chunk, performs `pg_dump` / restore and requires both rows plus Alembic head `0045_academy_content_locale_expansion` to survive.

## Next localization layer

The next production layer is tenant-scoped localization governance, not another global language list. It should provide:

1. tenant default content locale and enabled content-locale set;
2. translator/reviewer roles and approval workflow for policy/SOP translations;
3. source-language -> translated-version lineage and stale-translation invalidation when the source changes;
4. per-locale content completeness, caption/transcript and linguistic-QA telemetry;
5. tenant-specific fallback policy for display metadata only;
6. exact-locale evidence retrieval for regulated/company-policy Q&A;
7. explicit field acceptance for each UI release locale and each RTL rollout.

Until these gates are satisfied, repository support for a content locale must not be reported as field-tested language readiness.
