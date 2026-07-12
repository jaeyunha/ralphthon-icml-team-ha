# Charter INTEGRATE — continuous integration owner

Runs continuously from end of W0. Owns `main`, merges lane branches, owns
schema changes, runs live-paper milestones.

## Owns
`main` branch, `packages/contracts` + `packages/schemas` after freeze,
`plans/schema-change-requests/`, `scripts/run-review.sh`, milestone runs.

## Responsibilities
1. Merge lane branches when their charter's done-when passes from a clean
   checkout of the merge result (not just the lane's own worktree).
2. Arbitrate schema-change requests: apply to packages/schemas, regenerate
   types, notify affected lanes. Sole authority over frozen contracts.
3. Keep fixtures coherent: when a lane updates a shared fixture (e.g. the
   34584 bundle), re-run downstream lane tests before merging.
4. `scripts/run-review.sh` (§30 CLI): wire freeze → watchdog → phases as
   lanes land.
5. Milestones:
   - M1 (post-W1): freeze+extract+parse-verify+dossier on one real paper.
   - M2 (post-W2): reviewer round + rebuttal + follow-ups live on one
     real paper, watched in the viewer.
   - M3 (post-W3): full decision chain on 3 papers (spotlight/regular/
     reject), historical mode, comparison report.
6. Cross-lane conflict resolution and STATUS.md aggregation into
   `plans/STATUS-BOARD.md`.

## Done when
M3 passes and every charter's STATUS.md reports done.
