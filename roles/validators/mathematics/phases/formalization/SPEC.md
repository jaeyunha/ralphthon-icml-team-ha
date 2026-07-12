# Formalization Phase Specification

## Five-step protocol

1. Formalize the selected paper theorem in Lean 4.
2. Separately audit statement alignment against the anchored paper claim.
3. Attempt the proof.
4. Compile in the digest-pinned, network-disabled, read-only Lean container with dropped capabilities and resource limits.
5. Report `proof_validity` and `formalization_fidelity` as distinct fields.

## Outputs

Retain Lean source hash, container digest/version, alignment evidence, compile command constraints, exit code, stdout/stderr, proof validity, and fidelity. A compiling mismatched statement is `statement_mismatch`, not `verified_formally`.

## Completion

The protocol artifact is complete and referenced by a frozen-schema finding through `artifact_refs`; no field conflates compilation with paper-theorem verification.
