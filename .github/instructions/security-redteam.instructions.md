# Security and Red Team Instructions

## Threat Model

Assume:

- User input may be hostile.
- Uploaded files may contain prompt injection.
- External content may be malicious.
- Suppliers should not see each other's data.
- Internal roles may have different permissions.
- AI-generated output may be wrong.

## Risks to Check

- Prompt injection
- Secret leakage
- Role bypass
- Supplier data leakage
- Overbroad API response
- Unsafe file upload
- SQL injection-like query construction
- Missing authorization on backend route
- Insecure direct object reference
- Sensitive error messages
- Unreviewed AI tool execution

## Required Backend Checks

For every protected endpoint:

- Who is the user?
- What role do they have?
- Which warehouses/vendors can they access?
- Is the requested object inside their scope?
- Is the action allowed?
- Is the action audited?

## Red Team Questions

Ask:

- Can a supplier see another supplier's PO?
- Can a user change URL params to access another warehouse?
- Can an uploaded Excel file overwrite valid records?
- Can AI reveal hidden data from restricted documents?
- Can a prompt injection override system behavior?
- Can an error message leak internal table names or secrets?

## Secret Handling

Never commit:

- API keys
- service account JSON
- tokens
- passwords
- private credentials
- .env files with real values

Use .env.example for documentation.

## AI Safety

Never trust AI-generated SQL, code, or operational recommendations without validation.
