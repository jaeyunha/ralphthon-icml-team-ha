# Statistical Validator Role Specification

## Identity
One persistent logical `validator-statistics` identity owns every phase and the final finding ledger. Phase changes never create a new identity.

## Phases
`planning` → `data-integrity` → `inference-audit` → `robustness` → `confirmation` → `bundle-publication`.

## Invariants
- Read only paths in the hashed phase `allowed-inputs.json`.
- Resolve every paper anchor through the frozen dossier.
- Emit only frozen `validation-finding` objects; never emit an ICML score.
- Record limitations and every robustness axis actually tested.
- Confirm major or critical negative findings through two independent paths.
- Preserve narrower evidence when claim breadth is broader; do not extrapolate.
