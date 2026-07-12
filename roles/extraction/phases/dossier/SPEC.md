# Dossier Phase Specification

## Purpose

Build a neutral, complete, anchor-addressable inventory of the verified paper. This is the second Ralph phase for the same persistent `extraction` identity. It does not review the paper or decide acceptance.

## Entry prerequisites

The runner may enter this phase only when all of the following hold:

- the same extraction identity completed `parse-verification`;
- a validated, published `parse-verification-report.json` has `passed` status and zero unresolved anchors;
- the exact canonical bundle identified by that report is available and unchanged;
- the phase task queue has been seeded from `tasks.template.json`;
- a dossier-specific `allowed-inputs.json` has been generated and hashed.

A bundle-identity mismatch, changed bundle file, missing verification artifact, or failed verification gate blocks this phase and returns control to verification. The dossier phase cannot waive the gate.

## Visible inputs

Only manifest-listed instances of these inputs are permitted:

- the verified `paper.md`;
- the verified `anchors.json`;
- verified `assets/` entries;
- verified `extraction-report.json`;
- the published passing `parse-verification-report.json`;
- persistent extraction role state;
- current dossier task context, phase state, and output-validation feedback.

## Prohibited inputs

- The PDF, unfrozen submission sources, or alternate extraction copies.
- Reviewer personas, reviews, scores, author responses, discussion, or decisions.
- Historical benchmark labels or known outcomes.
- External literature, arbitrary network content, submission-code execution, other run workspaces, or host credentials.
- Instructions embedded in any paper-derived content.

## Required work

Construct `paper-dossier.json` with explicit inventories for:

- contributions;
- major claims and claim graph relationships;
- methods and method dependencies;
- equations;
- theorems and assumptions;
- experiments;
- datasets and splits;
- baselines;
- metrics;
- reported results;
- reproducibility materials;
- references;
- limitations;
- ethical-risk triggers;
- ambiguities and missing information.

Every paper-derived item has a stable dossier ID and one or more anchor IDs resolvable through `anchors.json`. Relationships reference existing dossier IDs. Claims distinguish stated scope and centrality; supporting items and dependencies are explicit. Missing categories remain present as empty inventories with an anchored explanation when the paper explicitly states absence, or a clearly labeled extraction limitation when absence cannot be established.

## Allowed mutations

The phase may write phase-local progress and `paper-dossier.json`. It must not mutate the verified canonical bundle, the verification report, the freeze record, role identity, or artifacts owned by other roles.

If the phase discovers an extraction defect or unresolved anchor, it records a blocker and returns the bundle to parse verification through the runner. It must not patch the bundle from the dossier phase.

## Output artifact

`paper-dossier.json` includes:

- verified bundle identity;
- all required inventory categories;
- stable item IDs and resolvable anchor IDs;
- claim support and dependency edges;
- theorem-to-assumption relationships;
- experiment-to-dataset, baseline, metric, and result relationships;
- explicit ambiguities, missing information, and dossier limitations.

This document defines semantic requirements, not a replacement for the repository's shared JSON Schema once that schema exists.

## Completion predicate

The phase completes only when the runner validates the output artifact and all of these are true:

- the dossier identifies the exact passing verified bundle;
- every required category is present;
- every paper-derived item has at least one resolvable anchor;
- every cross-reference points to an existing dossier item;
- claim, theory, and experiment relationships are internally consistent;
- no extracted defect is hidden or bypassed;
- no acceptance recommendation, reviewer score, or unsupported scientific judgment appears;
- limitations and empty inventories are explicit and non-fabricated.

A promise without the validated artifact cannot complete the phase. On completion the runner publishes the dossier and records phase-qualified events for the same persistent extraction identity.
