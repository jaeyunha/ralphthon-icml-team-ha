# Calibration stats from real ICML 2026 reviews — three decision tiers

Computed from the full-thread harvests in `data/`:

| Tier | Decision | Forums | Reviews | Rebuttals | Coverage |
|------|----------|--------|---------|-----------|----------|
| Spotlight | Accept (spotlight) | 504 | 1,944 | 1,941 | 504/538 enumerated |
| Regular | Accept (regular) | 315 | 1,209 | 1,196 | sample of 5,805 enumerated |
| Reject | Reject | 214 | 821 | 793 | 214/214 complete |
| **Total** | | **1,033** | **3,974** | **3,930** | |

Ground-truth priors for the Paper Committee agents (`ARCHITECTURE.md`).

## Review form (observed in 100% of reviews, all tiers)

`summary`, `strengths_and_weaknesses`, `soundness`, `presentation`,
`significance`, `originality`, `key_questions_for_authors`, `limitations`,
`overall_recommendation`, `confidence`, `final_justification` (post-rebuttal,
~80%), rare ethics fields. Matches `ARCHITECTURE.md` §1 exactly.

## Axis score distributions (1–4 scale)

| Axis | tier | 1 | 2 | 3 | 4 |
|------|------|---|---|---|---|
| Soundness | spotlight | 0% | 13% | 65% | 22% |
| | regular | 1% | 25% | 65% | 9% |
| | reject | 5% | 38% | 52% | 5% |
| Presentation | spotlight | 1% | 14% | 61% | 24% |
| | regular | 2% | 21% | 65% | 12% |
| | reject | 8% | 30% | 54% | 7% |
| Significance | spotlight | 0% | 20% | 63% | 16% |
| | regular | 2% | 34% | 57% | 7% |
| | reject | 6% | 44% | 46% | 4% |
| Originality | spotlight | 0% | 19% | 65% | 16% |
| | regular | 1% | 31% | 60% | 8% |
| | reject | 4% | 40% | 50% | 6% |

## Overall recommendation (1–6 scale)

| tier | 1 | 2 | 3 | 4 | 5 | 6 | per-paper mean | papers with mean ≥ 4 |
|------|---|---|---|---|---|---|----------------|----------------------|
| spotlight | 0% | 0% | 3% | 37% | 56% | 5% | **4.62** | 99.8% |
| regular | 0% | 3% | 11% | 60% | 25% | 1% | **4.10** | 75.2% |
| reject | 2% | 14% | 29% | 41% | 13% | 1% | **3.52** | 27.1% |

Perfectly monotone tier ordering — and heavily overlapping distributions.

## Confidence (1–5): identical across ALL tiers

Mode 4 in every tier (47%/46%/43%); grade 5 stays 7–9%. Reviewer confidence
carries **zero** signal about the decision.

## What separates accept from reject (rules for our committee)

1. **Individual reviews barely separate tiers.** 55% of reviews on rejected
   papers still say Weak Accept or better; 14% of reviews on regular accepts
   say Weak Reject or worse. Only the committee aggregate separates.
2. **Soundness and Significance are the discriminating axes.** Axis ≤ 2 rate
   climbs 13% → 26% → 43% (Soundness) and 20% → 36% → 50% (Significance)
   across spotlight → regular → reject. Presentation/Originality separate less.
3. **Averages cannot decide the borderline.** The best naive threshold
   ("paper mean rec ≥ 3.75 → accept") scores **88.0%** over all 1,033 papers —
   but only **76.7%** on the hard regular-vs-reject boundary. 27% of rejects
   score mean ≥ 4; 25% of regular accepts score mean < 4. At the borderline
   the AC decision turns on *which concerns survived rebuttal*, not the mean —
   this is precisely what the blocking-flaw override and contested-thread
   machinery in `ARCHITECTURE.md` §5–6 model.
4. **Benchmark bar:** the committee must beat 88% overall / 77% borderline
   naive accuracy while producing grounded rationale.

## Calibration rules for agent prompting

- **3 is the modal axis score in every tier.** Grade 4 rates: 16–24%
  (spotlight), 7–12% (regular), 4–7% (reject). Anchor: 3 = solid,
  4 = exceptional.
- Even spotlight papers draw 13–20% axis-2s; zero-disagreement runs on strong
  papers are suspicious.
- Recommendation 6 is rare everywhere (≤ 5%). Recommendation 4 (Weak Accept)
  is the modal grade for accepted papers — agents should live in the 3–5 band.
- Confidence mode is 4; a 5 should be exceptional and must not sway decisions.

## Review anatomy (for prose generation)

- Median `strengths_and_weaknesses`: 229 (spotlight) / 235 (regular) /
  253 (reject) words — reviewers write slightly more when rejecting.
- `key_questions_for_authors`: numbered Q1–Q5 style, typically 3–5.
- Median rebuttal ≈ 670 words (~3× review length).
- Thread arc per reviewer: `Official_Review → Rebuttal →
  Rebuttal_Acknowledgement → Reply_Rebuttal_Comment`.
- `final_justification` explicitly mentions score movement in 28% / 29% / 24%
  of reviews by tier — the rebuttal stage (§7) moves outcomes everywhere.

## Corpus caveats

- Regular tier is a ~5% sample (315 of 5,805 poster accepts), harvest order —
  treat regular-tier percentages as estimates (±~3pp at 95% for axis shares).
- Spotlight checkpointed at 504/538; reject complete.
