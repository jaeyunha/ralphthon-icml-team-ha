# Initial Review Phase

## Entry and output

Entry requires a frozen persona and frozen paper. The phase completes the queue in order, one task per invocation, then publishes immutable `published/official-review.json`, matching concern and question ledgers, and an initial score-history entry.

## Visibility

Allowed: own identity/state/persona/ledgers, frozen paper and supplement, common policy and rubric, admissible broker literature, and the published validator bundle. Forbidden: other personas, other reviews, author responses, AC opinions or issues, benchmark decisions, and other reviewers' query histories. The generated `allowed-inputs.json` must say `other_reviews=no`, `author_response=no`, and `internal_discussion=no`; the runner mounts only manifest paths.

## Completion gate

The summary is accurate, non-critical, and not copied from the abstract. All four score dimensions and the whole-paper obligations are discussed. Major claims are audited. Material weaknesses have resolving anchors and identical concern-ledger entries. Severity matches impact; questions are decision-relevant; scores match prose; overall is not averaged; confidence matches expertise and verification depth. External claims use verified sources, validator evidence is interpreted, no peer-review content is present, and schema validation passes. Failure reopens the current task with exact checker feedback.
