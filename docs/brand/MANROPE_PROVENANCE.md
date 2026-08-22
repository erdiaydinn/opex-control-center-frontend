# Manrope font asset provenance

EAY Brand v1 names **Manrope** as the canonical product typeface. Repository truth currently remains `SELF_HOST_BINARY_PENDING`; this document records the reviewed upstream artifact so a later binary admission is deterministic rather than a runtime CDN dependency.

- Upstream repository: `google/fonts`
- Upstream path: `ofl/manrope/Manrope[wght].ttf`
- Reviewed upstream blob SHA: `23dcf5e05a97f19a3567d40ebb3765580a4325f7`
- Upstream file size observed on GitHub: 162 KB
- License: SIL Open Font License 1.1 (`OFL-1.1`)
- Upstream license path: `ofl/manrope/OFL.txt`
- Reviewed upstream license blob SHA: `472064afc4b8dec9079fab03b8ffafb617a1b2d8`
- Runtime policy: external Google Fonts / CDN loading is forbidden.

## Admission rule

Do not set `config/eay_brand_v1.json -> typography.asset_state` to a self-hosted/accepted value until the exact reviewed font binary and its OFL license are committed inside this repository and the brand contract verifies their presence. A fallback system font is permitted while the binary remains pending; it must never be presented as bundled Manrope evidence.

The GitHub connector used for this workstream cannot copy a foreign repository binary object into this repository by SHA; GitHub correctly rejected that attempt as an invalid local blob. This limitation does not justify a remote runtime font dependency or an unverified substitute.
