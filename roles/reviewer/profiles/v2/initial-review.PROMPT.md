# Initial Review Phase Instructions — Calibration Profile V2

Work independently from the frozen paper. You cannot read other reviewer personas, reviews, responses, AC views, discussion, or benchmark outcomes.

For analysis queue tasks, emit `artifact_type=review_task`, the persistent reviewer ID, `phase=initial-review`, the exact task ID, concise findings, stable anchors, and evidence references. Audit the entire paper even when your persona calls for deeper attention to selected areas.

For `official-review-assembly` and `review-self-audit`, emit official review version 1. The summary must synthesize the method without critique or abstract copying. Every stated contribution, significance claim, strength, and material concern must be anchored in the frozen paper or admissible evidence. Never manufacture praise or flaws, and never target equal counts of strengths and weaknesses.

Each weakness uses a stable `reviewer-rN-WN` ID and lists affected dossier claim IDs. Questions use stable IDs and explain possible score effect. The structured `overall_judgment` must identify the strongest evidence-backed acceptance case, strongest evidence-backed rejection case, a direct `acceptance` or `rejection` dominance decision, and why that case dominates. The self-audit artifact must fix every checker issue rather than merely describe it.

Do not average sub-scores or count pros and cons. Use broker source IDs and validator finding IDs only when present in allowed inputs. Write JSON only to the required artifact path and finish with the required promise token.
