# Claim Extraction Phase Specification

## Purpose

Create the coordinator-owned mathematical claim inventory from the verified dossier. This is the first phase of the existing persistent identity.

## Inputs

Manifest-listed `paper-dossier.json`, `anchors.json`, equation assets, role state, task context, policy, prompts, and output schema. Reviews, responses, decisions, benchmark labels, network content, and unfrozen paper copies are prohibited.

## Work and output

Record definitions, equations, lemmas, theorems, assumptions, dependencies, complexity and convergence claims, and statistical derivations. Preserve dossier IDs, exact statements, pages, and resolving anchors. Publish `claim-inventory.json`; do not judge validity yet.

## Completion

Every inventoried item resolves to the anchor map, duplicate identities are rejected, all mathematical categories are represented even when empty, and no scores or recommendations appear.
