#!/bin/bash
# INTEGRATE: spawn a lane worktree + cmux workspace + GJC session.
# Usage: scripts/integrate-spawn-lane.sh <lane-slug> <CHARTER-NAME>
# Example: scripts/integrate-spawn-lane.sh w2-cf-reviewers W2-CF-REVIEWERS
set -euo pipefail
LANE="${1:?usage: $0 <lane-slug> <CHARTER-NAME>}"
CHARTER="${2:?usage: $0 <lane-slug> <CHARTER-NAME>}"
REPO_ROOT=$(git rev-parse --show-toplevel)
BRANCH="lane/$LANE"
WT="$HOME/wt/ralphthon-icml/lane-$LANE"

[ -f "$REPO_ROOT/plans/charters/$CHARTER.md" ] || { echo "no charter $CHARTER" >&2; exit 1; }
if git -C "$REPO_ROOT" show-ref --verify --quiet "refs/heads/$BRANCH" || [ -e "$WT" ]; then
    echo "COLLISION: $BRANCH or $WT exists" >&2; exit 1
fi

git -C "$REPO_ROOT" worktree add -q -b "$BRANCH" "$WT" main

cat > "$WT/.gjc-launch-prompt.md" <<EOF
You are lane $CHARTER in worktree $WT on branch $BRANCH (base: main).

Your charter: plans/charters/$CHARTER.md — read it in full first, then read
PHASED_ROLE_ARCHITECTURE_AND_AGENT_CONTRACTS.md and the cited sections of
RALPH_REVIEW_AGENT_SYSTEM_PLAN_AND_TECHNICAL_SPEC_V2.md, plus
plans/IMPLEMENTATION_PLAN.md coordination rules.

packages/contracts and packages/schemas are FROZEN on main. Schema change
needs go to plans/schema-change-requests/ as files; never edit schemas.
Develop against committed fixtures from other lanes (tests/fixtures/).
Stay strictly inside your charter's owned paths. Use /skill:team to
parallelize independent slices when beneficial. Commit checkpoints on this
branch; do NOT merge to main. Every done-when item must pass from a clean
checkout. Finish by writing plans/charters/STATUS-$CHARTER.md.
EOF

cmux new-workspace --name "gjc-$LANE" --cwd "$WT" --focus false \
    --command "GJC_TMUX_SESSION='gjc-ricml-$LANE' gjc --tmux \"\$(cat .gjc-launch-prompt.md)\""
echo "spawned $LANE ($CHARTER) at $WT"
