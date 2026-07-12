# Code Executor Runtime Policy

## Default profile: 30-minute paper review

The code executor is a bounded verification probe, not an open-ended reproduction lab. The complete paper review must finish within 30 minutes, so code execution receives a hard nine-minute wall-clock budget, including environment preparation, local or remote scheduling, execution, evidence capture, and cleanup.

The executor follows this evidence ladder and stops at the strongest result reached before the deadline:

1. **Static verification (target: 2 minutes):** freeze the repository, record provenance and hashes, identify entry points and declared dependencies, compare important defaults with paper anchors, and determine dataset/checkpoint/GPU requirements.
2. **Environment and import smoke test (target: 2 minutes):** use a cached or already available image, import or compile the core modules, instantiate the main component, and load the declared configuration.
3. **Minimal execution (target: 3 minutes):** run the cheapest meaningful probe: one forward pass, one inference example, one training step, one tiny batch, checkpoint loading, or a very small evaluation slice.
4. **Claim spot-check (only with remaining time):** compare one bounded observed output or metric with one anchored paper claim. Never generalize a subset result into full reproduction.
5. **Evidence and cleanup (reserve: 1 minute):** persist logs, hashes, exit state, resource use, limitations, backend identity, and cleanup outcome.

## Hard limits

- Executor wall clock: 9 minutes.
- Environment preparation: 2 minutes.
- Maximum research commands: 3.
- Maximum duration per command: 3 minutes.
- Command retries: 0.
- Download budget: 1 GiB total.
- Full training, full-dataset evaluation, hyperparameter sweeps, repeated seeds, and large dependency builds are prohibited.
- Preserve the best achieved verification status when time expires. Record phase termination reason `budget_exhausted`; do not relabel an unattempted expensive experiment as `execution_failed`.

## Execution backends

### Local Docker

The hardened Docker sandbox remains the default. It must retain the existing non-root, no-network, read-only-input, isolated-workspace, resource-quota, timeout, logging, and hashing controls.

### VESSL batch jobs

The official `vesslctl` Agent Skill and CLI may be used only when a bounded probe genuinely requires CUDA, more VRAM than the local runner provides, or a GPU unavailable locally.

VESSL use is subject to all of these constraints:

- Use a non-interactive **batch job**, never a persistent workspace.
- Use a pre-existing image and already staged inputs; do not spend the review budget building an image or uploading a large dataset.
- Request one GPU by default.
- GPU scheduling wait limit: 90 seconds.
- Remote command wall clock: 5 minutes, still contained within the nine-minute executor budget.
- Maximum cloud cost per paper: USD 1 unless the run manifest explicitly authorizes another amount.
- Submit at most one VESSL job and do not retry it.
- Before job creation, present the exact command, selected resource specification, hourly price, and maximum estimated cost. Require explicit operator approval unless the run was started with an equally explicit VESSL pre-authorization and cloud-cost ceiling.
- Do not inject organization secrets or forward host credentials.
- Capture organization/team, job slug, resource specification, GPU type/count, image reference/digest when available, exact command, timing, logs, metrics, exit state, output hashes, estimated/actual cost, and termination/cleanup result.
- Cancel the job immediately on timeout, budget exhaustion, wrong resource selection, unexpected long download/build, or loss of supervision.

VESSL is not presumed equivalent to the local no-network sandbox. If the required egress denial and isolation controls cannot be demonstrated, do not run arbitrary or unreviewed repository code there. Limit the remote probe to vetted commands and inputs, or return the best local status with a typed backend limitation. VESSL must never be used to bypass a sandbox control.

## Backend escalation reasons

Remote GPU escalation requires one recorded reason:

- `cuda_unavailable`
- `insufficient_vram`
- `gpu_unavailable_locally`
- `multi_gpu_required` (still requires explicit manifest authorization for more than one GPU)

Missing data, missing checkpoints, unclear commands, dependency ambiguity, or an experiment that cannot finish within the remaining budget are not reasons to allocate a cloud GPU.

## Authentication boundary

If `vesslctl auth status` is unauthenticated, stop before any cloud operation and request the operator to complete `vesslctl auth login`. Installing or inspecting the CLI and Agent Skill does not require authentication. Never initiate login by embedding, printing, or requesting access tokens.
