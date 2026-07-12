# Confirmation Phase Specification

## Purpose

Resolve independent confirmation paths and enforce the high-impact severity gate before publication.

## Rules

A primary symbolic, SMT, numerical, shape, code, or Lean result is one path. Any `major` or `critical` negative finding must cite at least one different completed path that reproduces the defect or establishes the missing assumption/mismatch by another method. A duplicate rerun with the same tool and assumptions is not independent.

## Completion

Every confirmation reference resolves to retained phase evidence. Unconfirmed high-impact candidates are downgraded or remain unpublished; they are never silently promoted.
