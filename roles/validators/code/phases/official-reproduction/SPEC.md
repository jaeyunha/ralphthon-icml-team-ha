# Official Reproduction Phase

## Inputs

Frozen official repository, provenance and license records, paper anchors, sandbox image, static command plan, and declared hardware/dataset inventory.

## Work

Freeze exact commit and deterministic tree hash; build or identify the isolated image; run repository tests, a smoke evaluation, and each feasible central-result command only in the sandbox. Capture argv, image digest, environment manifest, hardware, datasets, stdout/stderr, duration, exit state, and hashes.

## Completion

Completion requires an attempted sandbox execution or an explicit typed `sandbox_unavailable`/`not_executable` result. Inspection alone cannot masquerade as reproduction. Documentation scale and verification status are both recorded.
