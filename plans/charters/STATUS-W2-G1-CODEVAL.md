# STATUS W2 G1-CODEVAL

## Result

**PASS.** Lane G1 is implemented in its owned paths. The persistent code-validator role, hardened Docker sandbox, official reproduction loop, clean-room input/freeze protocol, four-way conformance comparator, reproducibility audit, schema/no-score gate, planted fixtures, and real paper-34783 evidence are committed.

## Done-when evidence

### Hardened sandbox

`engine/validators/sandbox/runtime.py` requires Docker rootless mode on native Linux or the Docker Desktop Linux-VM boundary on macOS and always runs research processes as uid/gid `65532:65532`. Runtime controls include:

- `--network none` and no forwarded host environment or credentials;
- read-only root filesystem and declared read-only input mounts;
- isolated size-limited `/workspace` and `/tmp` tmpfs mounts;
- CPU, memory, PID, and hard wall-clock limits;
- all capabilities dropped, `no-new-privileges`, and Docker default seccomp;
- captured exact argv, image digest, stdout/stderr, duration, exit status, and SHA-256 log hashes.

`engine/validators/tests/test_sandbox_runtime.py` executes real Docker containers and proves host/credential and network denial, read-only input enforcement, workspace disk quota, cgroup memory quota, and timeout termination.

### Official reproduction and reproducibility status

The official local `equities-jepa` artifact for paper 34783 was frozen at integrated repository commit `7f8d0ecb1197bb5eca96aff08b0d7f7faf864b05` plus deterministic artifact tree hash `sha256:06d973e05f8bc1eb79da9e8a9d4dbc390dccb0f5030190fe2a8ec648277d81c9`.

A pinned `python:3.12-slim` image was built from `tests/fixtures/validators-code/real-34783/Dockerfile`. The first build truthfully failed because `numcodecs` required an aarch64 native build without `gcc`; the second build added the required toolchain and succeeded as image digest `sha256:b67a1537eb454817ade05ffad8a2fbd9d5bb82d43e5bdbffb125b4e8487a3045`. Build evidence is in `environment-build.json`.

The real sandbox run recorded in `reproduction-report.json` passed:

1. static compilation of all 15 official Python source files; and
2. loading the bundled synthetic dataset with observed shape `(1400, 512, 28)`, tokenizer forward to `(1, 4, 32)`, and temporal JEPA encoder forward to `(1, 13, 32)`.

The graduated verification status is accurately `partial_execution`, not a fabricated central-result reproduction. Documentation quality is separately `2/4`: the repository supplies setup/training commands and synthetic data, but the proprietary Massive.com data, trained checkpoints, and complete evaluation pipeline needed for the paper's central metrics are absent.

### Clean-room and conformance

- `allowed_inputs.py` accepts only paper, supplement, algorithm, equation, and environment evidence; it rejects official source/README/config/issues/PRs/third-party implementations and verifies input hashes.
- Clean-room implementations are frozen by deterministic hash before comparison. The committed fixture records `independently_reimplemented` and a source hash.
- `conformance.py` compares paper, official, clean-room, and observed structured specifications. The planted L1-paper/L2-official discrepancy is emitted as `equation_code_mismatch` with official-source and independent-clean-room confirmation paths.

### Findings and identity

- All committed findings validate against the frozen `validation-finding.schema.json` without modifying `packages/contracts` or `packages/schemas`.
- Findings include paper anchors, artifact references, method, observation, limitations, confirmation paths, and confidence.
- The coordinator recursively rejects ICML score/rating/recommendation fields.
- `tests/fixtures/validators-code/persistent-role/` proves the same `code-validator-34783` logical identity and finding ledger persist across all four phases.

## Verification

Passed on 2026-07-11:

```text
uv run pytest engine/validators/tests -q
13 passed in 7.38s

uv run ruff check engine/validators
All checks passed!

uv run pytest tests/test_contract_schemas.py -q
89 passed in 0.62s

uv run pytest -q
106 passed in 3.51s

uv run ruff format --check engine/validators
14 files already formatted
```

The real reproduction command was:

```text
uv run python -m engine.validators.code --paper-id 34783 ... --image ralphthon/equities-jepa-validator:34783 ...
```

Both research-code commands have `status: passed`, `network: none`, non-root uid/gid, immutable input mount, resource controls, and captured hashes in the committed report.
