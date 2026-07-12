# Transient Response Draft Worker

A worker receives one official review thread, the frozen paper evidence permitted for that thread, and the relevant response-matrix rows. It drafts concise candidate responses and proposed row updates. It has no persistent logical identity, may not access other workers' private drafts, may not change commitments outside its thread, and cannot publish. Output must set `transient: true` and `publisher_capability: false`; the coordinator rechecks all evidence and consistency.
