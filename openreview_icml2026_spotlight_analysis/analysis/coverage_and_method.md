# Coverage And Method

## Current Harvest State

- Accept Spotlight: 538 submissions; 538 forums harvested; 8490 notes.
- Accept Regular: 5805 submissions; 5805 forums harvested; 93779 notes.
- Reject: 214 submissions; 214 forums harvested; 3396 notes.

## Data Directories

- Spotlight full threads: `data/full_forum_threads/*.json`
- Regular full threads: `data/regular_full_forum_threads/*.json`
- Reject full threads: `data/reject_full_forum_threads/*.json`
- Summary counts: `data/full_harvest_summary.json`
- Bulk endpoint stats: `data/bulk_parent_invitation_harvest_summary.json`

## Method

1. Enumerated tab submissions via OpenReview public search and strict local filtering:
   - Spotlight: exact phrase `"ICML 2026 spotlight"`.
   - Regular: exact phrase `"ICML 2026 regular"`.
   - Reject: exact phrase `"Submitted to ICML 2026"` plus `venueid == ICML.cc/2026/Conference/Rejected_Submission`.
2. Used browser-cleared OpenReview API bulk endpoints:

```text
https://api2.openreview.net/notes?parentInvitations=ICML.cc/2026/Conference/-/<TYPE>&limit=1000&offset=<N>&count=true
```

where `<TYPE>` is `Official_Review`, `Rebuttal`, `Rebuttal_Acknowledgement`, `Reply_Rebuttal_Comment`, or `Decision`.

3. Grouped those notes back by `forum`, inserted the top-level submission note, sorted by `cdate`, and wrote one JSON file per forum.

## Completeness Notes

- This captures all public OpenReview notes in the five review/rebuttal/decision invitation families returned by the API for the ICML 2026 conference.
- It intentionally focuses on reviews and replies. Miscellaneous public comments outside those invitation families, if any, are not part of the review/rebuttal corpus.
