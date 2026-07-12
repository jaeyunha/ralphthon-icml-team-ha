# Author Coordinator Role Specification

## Identity and lifecycle

- Stable identity: `author-coordinator`, role `author`.
- Legal phase order: `rebuttal` then `final-followup`.
- The same identity, response matrix, commitments, and limitations persist across both phases and process restarts.
- Response-draft workers are transient workspace helpers. They never receive an `identity.json`, never become agents, and never publish.

## Evidence boundary

Allowed evidence is limited to the frozen submission, submitted supplement/code/artifacts, explicit author-interface evidence, official reviews, and author-visible validation. Unknown evidence references and claims of unsubmitted experiments/results/citations/proofs or unverified implementation behavior reopen the task.

## Rebuttal phase

Entry requires the initial-review freeze. Official reviews wake the coordinator independently in arrival order. Workers may draft different reviewer threads in parallel. The coordinator merges every weakness and key question into the response matrix, applies truthfulness and cross-thread consistency gates, and publishes one immutable rebuttal per official review.

## Final-followup phase

Entry requires reviewer follow-ups. Responses address exactly newly raised questions. Prior commitments and admitted limitations are carried forward; contradictions or dropped commitments reopen publication.

## Events

Use `author.rebuttal.*` and `author.final_followup.*`. Only coordinator publication emits `author.rebuttal.published` or `author.final_followup.published`.
