# EAY Academy localization strategy

## Principle

Academy localization has two separate readiness tiers. A language may be valid for authored learning content, SOP evidence, transcripts, captions and quiz material without implying that the complete EAY product UI has passed translation QA in that language.

The default canonical locale remains `tr`. Existing persisted compact values such as `tr`, `en`, `de` and `ar` stay valid. Common BCP-47 regional inputs such as `tr-TR`, `en-US`, `fa-IR`, `ur-PK` and `pt-BR` are normalized at the API boundary rather than creating duplicate language identities.

## Core release locales

Critical UI translation completeness is a release gate for:

- `tr`
- `en`
- `de`
- `ar`
- `fr`
- `es`
- `it`
- `nl`
- `pl`
- `pt-BR`

A missing critical translation key in this tier must not silently degrade into a false "fully localized" claim.

## Extended Academy content/evidence locales

The backend contract additionally accepts a broader content/evidence catalog including Persian, Russian, Romanian, Bosnian Latin, Albanian, Georgian, Kurmanji, Sorani, Bulgarian, Armenian, Simplified Chinese, Serbian Latin, Macedonian, Indonesian, Hungarian, Azerbaijani, Ukrainian, Greek, Malay, Uzbek Latin, Hindi, Urdu, European Portuguese, Japanese, Korean, Czech, Slovak, Swedish, Danish, Norwegian, Finnish, Hebrew, Thai, Vietnamese, Bengali and Pashto.

This tier means that content metadata, document chunks, quiz text and grounded knowledge requests can carry a canonical locale. It does not by itself certify translated UI quality, linguistic accuracy, captions, screen-reader quality or legal/SOP translation approval.

## RTL

RTL is a locale property, not an Arabic-only special case. Academy declares RTL for:

- Arabic (`ar`)
- Persian (`fa`)
- Urdu (`ur`)
- Sorani Kurdish (`ckb`)
- Hebrew (`he`)
- Pashto (`ps`)

Staging acceptance still requires visual/layout testing, keyboard/focus validation and screen-reader checks. Backend direction metadata is not an accessibility-compliance claim.

## Fallback and truth boundary

Metadata/UI fallback is `requested -> en -> tr` for display-only fields. Learning evidence is stricter: SOP/document retrieval uses the exact requested canonical locale and does not silently cross languages. A missing source in the requested language must remain unsupported unless a separately versioned and approved translation exists.

Machine-generated translation may assist authoring, but published SOP/policy translation must retain source version, language, reviewer/approval provenance and cannot silently overwrite the authoritative source language.

## Tenant policy

The current foundation exposes the platform locale catalog globally and keeps persistence backward compatible. Tenant-specific enabled-locale policy, per-tenant default locale, translator/reviewer workflow and translation completeness telemetry are the next localization layer; they must be tenant-scoped and fail closed rather than inferred from browser language.

## Release gates

Before claiming a locale production-ready for a tenant:

1. critical UI key completeness must pass for the applicable release tier;
2. RTL locales must pass core-flow layout and interaction tests;
3. captions/transcripts and document accessibility must be validated for published learning assets;
4. SOP/policy translations must retain exact source-version provenance and approval evidence;
5. RAG answers must cite the exact language/version actually retrieved;
6. no tenant may see content or translation metadata belonging to another tenant.
