# STATUS — schema request 002

**State: APPROVED AND APPLIED BY INTEGRATE**

Approved the additive validator role identities in
`allowed-inputs.schema.json`; no permission or path-confinement relaxation was
needed.

Verification:

- `bun run --cwd packages/schemas generate:types`
- `bun test packages/schemas/test/schema.test.ts` — 27 passed
- `bun run --cwd packages/schemas check:types`
- `git diff --check`

The schema accepts the six bounded validator identities and explicitly rejects
the unbounded role string `validator`.
