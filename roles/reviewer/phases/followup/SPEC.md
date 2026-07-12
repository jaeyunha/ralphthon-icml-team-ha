# Reviewer Follow-Up Phase

Entry requires immutable official review v1 and the associated published rebuttal. The same reviewer identity may read its own review, concern and question ledgers, score history, own rebuttal thread, paper, and published validation updates. It still cannot read another reviewer's review or response thread by default; the manifest must contain no `other_reviews` category and must expose only `agents/author/published/rebuttals/{agent_id}.json`.

Every original concern is classified `resolved`, `partially_resolved`, `unresolved`, or `invalidated_by_response`, with response evidence, remaining gap, and score effect. The reviewer acknowledges responsive evidence, does not move goalposts, asks a new question only when decision-relevant, and explains every changed or unchanged score. Score history is append-only. Completion publishes follow-up v1 and updated ledgers without modifying official review v1.
