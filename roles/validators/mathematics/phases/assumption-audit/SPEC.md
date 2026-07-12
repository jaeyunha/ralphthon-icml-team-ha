# Assumption Audit Phase Specification

## Purpose

Audit the published claim inventory for undefined symbols, hidden assumptions, quantifier and scope errors, circular dependencies, boundary omissions, and unsupported generalization.

## Inputs and output

Read only manifest-listed dossier evidence, anchors, the published claim inventory, private role state, and checker feedback. Write phase-local audit evidence and candidate findings; do not mutate the dossier or inventory.

## Completion

Every central theorem has an explicit dependency/scope audit. Negative candidates cite resolving anchors and limitations. Major or critical severity remains blocked until confirmation.
