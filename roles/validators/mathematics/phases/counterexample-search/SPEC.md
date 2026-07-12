# Counterexample Search Phase Specification

## Purpose

Seek concrete failures or bounded support using exact arithmetic, high precision, interval-aware reasoning, property tests, exhaustive small domains, boundaries, and adversarial points.

## Requirements

Search domains and tolerances are explicit. Exact rational evaluation precedes floating approximation where possible. Boundary points, zero, unit values, sign changes, smallest domains, and singular regions are included when admissible. Retain the first minimal reproducible counterexample and sample coverage.

## Completion

A negative finding identifies concrete values and an anchored claim. Absence of a bounded counterexample yields only `supported_numerically` or `inconclusive`, never formal verification.
