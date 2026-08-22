# EAY Brand System v1

Status: **canonical design direction** for the EAY web/platform and field-mobile surfaces.

The image-generation concept boards are design references. Production UI must use repository-owned vector/token implementations; a concept-board PNG is not a production logo asset.

## 1. Brand architecture

| Surface | Brand | Mark | Use |
| --- | --- | --- | --- |
| Corporate / executive | **EAY** | Monogram | Company identity, corporate documents, executive material |
| Platform / web / personal mobile | **EAY One** | Flow Ring | Unified platform shell, web control center, phone product |
| Rugged field execution | **EAY Terminal** | Scan Mark | Inventory, picking, putaway, receiving, transfer, managed scanner devices |

Do not use EAY Terminal as the corporate master mark. Do not label the rugged Inventory application as EAY One. Debug/synthetic preview surfaces are not production brand evidence.

## 2. Color system

- EAY Navy — `#07235B` — dominant identity, headings, navigation, trusted surfaces.
- EAY Magenta — `#D20A6D` — restrained brand accent, emphasis, selected identity detail.
- EAY Electric Blue — `#1F6BFF` — operational/technology accent, scan and active-state cues.
- Charcoal — `#111827` — primary body ink.
- White — `#FFFFFF` — primary inverse/background.
- Surface — `#F8FAFC`.
- Border — `#E5E7EB`.
- Muted — `#6B7280`.
- Body — `#374151`.

Navy is the dominant color. Magenta and electric blue are not equal-weight background colors and must not turn the interface into a multi-gradient startup theme.

## 3. Typography

Canonical family: **Manrope**.

- Display / hero: 700–800.
- Section heading: 700.
- Navigation / button / label: 600.
- Body: 400–500.
- Tabular operational data may use 500–600 for scanning speed.

Fallback until the reviewed self-host binary is present in the repository:
`Avenir Next, Segoe UI, Helvetica Neue, Arial, sans-serif`.

The application must not fetch fonts from a third-party CDN at runtime. A future self-hosted Manrope asset must be reviewed and bundled under its applicable open-font license before the fallback state is removed.

## 4. Web product skeleton

### Header
- Left: EAY master mark / EAY One platform lockup according to context.
- Navigation: **Ürünler · Çözümler · Modüller · Güvenlik · Hakkımızda · İletişim**.
- Primary CTA: **Demo Talep Et**.
- Secondary CTA: **Platformu İncele**.

### Hero
- Primary headline: **Operasyonu tek merkezden yönetin.**
- Supporting line: **Saha, envanter, iş gücü ve karar akışlarını EAY One altında birleştirin.**
- Writing style: short, concrete, operational, evidence-aware. Avoid generic phrases such as “geleceğe taşıyan yenilikçi çözüm”.

### Page sequence
1. EAY nedir?
2. EAY One platform.
3. Modüller.
4. Saha uygulamaları / EAY Terminal.
5. Güvenlik ve yetki mimarisi.
6. Operasyon örnekleri ve evidence.
7. Demo / iletişim.

### Platform shell
Current authenticated Control Center is an **EAY One** surface. Its visible product identity must say EAY One, not OneOps/OPEX. Existing authorization, localization, accessibility and server-owned product-state boundaries remain unchanged by branding.

## 5. App design tokens

### Geometry
- Small radius: 12 dp/px.
- Default card/input radius: 16 dp/px.
- Large surface radius: 20 dp/px.
- Phone minimum touch target: 48 dp.
- Rugged/field primary touch target: 56–64 dp.

### Spacing
Use an 8-based rhythm: 4 / 8 / 12 / 16 / 24 / 32 / 48.

### Elevation
Use restrained navy-tinted shadows. Avoid large glow effects and decorative glassmorphism on operational execution screens.

### Components
- Primary button: navy background, white text.
- Secondary/action accent: electric blue.
- Brand emphasis only: magenta.
- Cards: white or near-white on `#F8FAFC`, clear border, strong hierarchy.
- Critical/error semantics continue to use semantic error colors; never reuse magenta as an error truth indicator.
- Scanner execution: large next action, no decorative clutter, explicit sync/recovery state.

## 6. Logo usage

### Clear space
Keep clear space around each mark at least equal to the height of the inner A counter/accent element. Do not let text, icons or card borders enter this zone.

### Minimum size
- Master monogram: 24 px minimum digital mark width.
- EAY One lockup: 96 px minimum digital width.
- EAY Terminal lockup: 112 px minimum digital width.
- Below lockup minimums use the mark-only app-icon form.

### Allowed
- Full approved palette.
- Navy/white or black/white monochrome forms.
- App-icon simplification that preserves the recognizable geometry.

### Prohibited
- Stretching/skewing.
- Re-coloring individual strokes outside the canonical palette.
- Making gradients necessary for recognition.
- Replacing the EAY mark with a generic sparkle/shield icon.
- Using EAY Terminal as the corporate logo.
- Calling a rugged debug APK EAY One.

## 7. Tone of voice

Use compact, operational prose:
- “Operasyonu tek merkezden yönetin.”
- “Hız, görünürlük ve kontrol aynı sistemde.”
- “Kurumsal kararları gerçek operasyon verisiyle alın.”

Avoid inflated claims. Repository/integration evidence must not be written as field/production evidence.

## 8. Acceptance

A branded surface is not complete merely because the palette changed. It must preserve:
- accessibility and reduced-motion behavior;
- ten-locale/RTL contracts where the surface is localized;
- authority/security boundaries;
- debug-versus-production product separation;
- exact-head build/lint/test acceptance.
