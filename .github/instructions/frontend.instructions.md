# Frontend Instructions

## Stack Assumptions

Frontend is a React-based OPEX Control Center interface.

Use module boundaries:

- `src/modules/Planogram`
- `src/modules/DockOS`
- `src/modules/Academy`
- `src/modules/Budget`
- Shared components should live separately.

## UI Rules

Prefer:

- Clean light theme by default
- Clear spacing
- Strong hierarchy
- Accessible contrast
- Semantic HTML
- Keyboard navigation
- Loading, empty, error, and success states
- Stable layout during loading

Avoid:

- Dark cyber theme as default
- Excessive animation
- Tiny dense tables without scanning aids
- Unclear buttons
- Hidden critical actions
- UI that depends only on color

## Animation

Use animation to guide attention, not to impress.

Good:

- Card entrance
- Row update pulse
- CountUp KPI
- Drawer transition
- Loading skeleton

Bad:

- Heavy background motion in operational screens
- Animations that delay work
- Effects that reduce readability

## Accessibility

Use:

- Buttons for actions
- Links for navigation
- Labels for inputs
- Focus states
- ARIA only when semantic HTML is insufficient
- Role-based Playwright locators where possible

## API Handling

Every API call should handle:

- Loading
- Empty data
- Error
- Timeout
- Unauthorized
- Forbidden

## Component Rule

Do not put business logic deeply inside visual components.

Prefer:

- API client
- hook/state adapter
- pure component
- small reusable UI pieces
