#!/bin/bash
# INTEGRATE lane poll: report per-lane commits, STATUS files, and dirty state.
set -euo pipefail
WT_ROOT="$HOME/wt/ralphthon-icml"
LANES=(w0-contracts w1-d-watchdog w1-b-extraction w1-j-database w1-e-broker w1-k-viewer)

for lane in "${LANES[@]}"; do
    wt="$WT_ROOT/lane-$lane"
    if [ ! -d "$wt" ]; then
        echo "$lane: MERGED/REMOVED"
        continue
    fi
    commits=$(git -C "$wt" log main..HEAD --oneline 2>/dev/null | wc -l | tr -d ' ')
    dirty=$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')
    status="none"
    for f in "$wt"/plans/charters/STATUS-*; do
        [ -e "$f" ] || continue
        name=$(basename "$f")
        # Ignore status files merely inherited from main (for example W0).
        if ! git -C "$wt" diff --quiet main...HEAD -- "plans/charters/$name" 2>/dev/null \
            || [ -n "$(git -C "$wt" status --porcelain -- "plans/charters/$name")" ]; then
            status="$name"
            break
        fi
    done
    frozen=""
    if [ "$lane" = "w0-contracts" ] && [ "$status" != "none" ]; then
        grep -qi "FROZEN" "$wt/plans/charters/$status" 2>/dev/null && frozen=" [FROZEN]"
    fi
    echo "$lane: commits=$commits dirty=$dirty status=$status$frozen"
done

echo "---"
ls "$(git rev-parse --show-toplevel)/plans/schema-change-requests" 2>/dev/null \
    || echo "schema-change-requests: empty"
