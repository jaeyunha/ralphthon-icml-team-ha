# Broker Process Role Invariants

The literature broker is a deterministic service role, not a reviewer identity. It owns policy enforcement, browser/API access, retrieval, evidence sanitization, and isolated provenance writes.

It may read only the current request, frozen run policy, frozen target fingerprint, its private service configuration, and the requesting reviewer’s broker directories. It must not read reviewer prose, scores, other reviewers’ workspaces, author responses, AC state, or known benchmark outcomes.

The Ever browser boundary is subordinate and untrusted. It runs fixed `page.goto`/`page.eval` automation without an LLM and returns arXiv DOM metadata as discovery input only. The broker independently applies target, cutoff, identity, retrieval, sanitization, hashing, and schema-validation gates; browser text can never bypass a gate or directly enter a reviewer prompt.

A request terminates with exactly one typed response or refusal artifact. Backend errors, malformed browser output, unavailable full text, and schema failures are explicit refusals or rejected-candidate reasons, never omissions.
