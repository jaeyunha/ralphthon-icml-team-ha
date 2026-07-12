# Deterministic Ever Browser Contract

This file documents the browser boundary; it is not an LLM prompt. Literature discovery uses `ever repl --fresh --json` and the governed Everwright browser API without an autonomous agent run.

The broker:

1. receives a conceptual query only after policy and target-fingerprint filtering;
2. URL-encodes that query into the fixed `https://arxiv.org/search/` endpoint;
3. invokes Ever with an argv array, never a shell;
4. navigates with `page.goto`, waits briefly, and runs a fixed bounded `page.eval` extractor over `li.arxiv-result` rows;
5. accepts only canonical `arxiv.org/abs/<id>` identities with title, authors, and a parseable `Submitted` date;
6. treats DOM metadata as discovery input only.

Ever does not download or supply evidence text. The broker independently fetches the canonical arXiv page and PDF over HTTP, verifies identity, enforces the frozen cutoff and target-duplicate filter, sanitizes fetched text, hashes content, and validates the final evidence packet.

The query is data inside an encoded URL. It is never interpolated into executable JavaScript or a shell command.
