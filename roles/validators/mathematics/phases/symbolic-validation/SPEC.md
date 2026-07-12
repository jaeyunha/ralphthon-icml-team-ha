# Symbolic Validation Phase Specification

## Purpose

Run tool-grounded symbolic algebra, calculus, matrix/probability, SMT, shape, and equation-to-code checks for inventoried claims.

## Required tools

Use pinned SymPy and Z3 versions. Compare algebraic equivalence through simplification, compute gradients/Hessians/derivatives/integrals where claimed, test logical implication by solving its negation, infer tensor dimensions, and compare equation expressions with permitted G1 implementation expressions.

## Outputs and completion

Retain machine-readable inputs, tool versions, simplified differences, models/counterexamples, inferred shapes, and limitations. Every finding is anchored and schema-valid. Unsupported syntax is `tool_unsupported`, never silently replaced with an ungrounded judgment.
