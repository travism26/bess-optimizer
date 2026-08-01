# Learning Research Index

Research produced 2026-08-01 by four parallel research agents, on how Travis
should learn the material this project generates (the PRs, Rust for M4, the
ERCOT domain, and the LP math) instead of merging past it. Each file stands
alone; this index is the map.

## The four documents

1. **[pr-review-learning-techniques.md](pr-review-learning-techniques.md)**
   Where the interactive HTML diff explainer idea comes from (Geoffrey Litt,
   "Understanding is the New Bottleneck", July 2026) and the evidence-backed
   technique catalog: predict-before-reading, teach-back, quiz-based recall.
   Ends in a 45-minute per-PR review ritual. The matching skill is installed
   at `.claude/skills/explain-diff-html/SKILL.md`.

2. **[repo-pr-study-guide.md](repo-pr-study-guide.md)**
   The backlog: study cards for the eight merged PRs (#1, #2, #4, #5, #7,
   #8, #9, #10) with concepts, comprehension questions, and answers. Study
   in merge order, about 5 hours total; #2 (LP formulation) and #9 (AS
   co-optimizer) are the two deep dives. Includes the going-forward ritual
   to add to the TASKS.md runbook.

3. **[rust-learning-plan-m4.md](rust-learning-plan-m4.md)**
   The M4 plan: which Rust resources to use and skip, the `highs` crate
   recommendation, the hand-write vs delegate split (you write the LP
   builder and PyO3 boundary, agents write scaffolding and harnesses), and
   a 4-week schedule at 6-8 hours per week.

4. **[domain-and-lp-learning.md](domain-and-lp-learning.md)**
   ERCOT and BESS economics resources (start with Potomac Economics' State
   of the Market report, ESR section), LP intuition resources, eight
   exercises built from this repo's own numbers, and an interview question
   bank. Key domain fact: the ERCOT battery revenue mix flipped from
   roughly 84 percent ancillary services in 2023 to under half by
   2024-2025, which reframes how to present M3's uplift number.

## Suggested sequence

- **This week:** adopt the 45-minute ritual (doc 1) and work through the
  PR backlog (doc 2) at one or two PRs per sitting.
- **Before starting M4:** week 1 of the Rust plan (doc 3), then author the
  M4 specs around its hand-write vs delegate split.
- **Ongoing, low intensity:** domain reading and the repo-grounded
  exercises (doc 4); the interview bank is the checklist for fall.

## Cross-cutting findings worth remembering

- Passive reading of AI output teaches little; every technique that
  survived scrutiny forces production: predict, explain back, answer
  questions cold, re-implement.
- The July 2023 fixture month sits in the peak-AS era of ERCOT. M3's
  uplift number is period-correct but not representative of 2025; say so
  when presenting it (doc 4 has the numbers and sources).
- The repo never reads dual values from HiGHS. Extracting shadow prices
  from the existing LP is both the fastest duality lesson and a natural
  future mini-feature (doc 4, exercise section).
