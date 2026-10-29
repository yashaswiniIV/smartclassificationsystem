# AI evaluation

Honest, reproducible numbers for the two AI claims, measured on a hand-labeled set
([dataset.json](dataset.json)) with the **same** embedding model the app uses
(`paraphrase-multilingual-MiniLM-L12-v2`, 384-d, via fastembed/ONNX). No DB, no API key.

```powershell
cd backend
uv run python ..\ml\eval\run_eval.py
```

## What it measures

1. **Category top-1 accuracy** — zero-shot: each complaint is embedded and matched to
   the nearest category *prototype* (the category name + description, embedded). No
   labeled training data is used.
2. **Duplicate detection** — every pair of complaints is labeled same-problem or not
   (from `duplicate_groups`). We sweep the cosine threshold and report precision /
   recall / F1, then the two configured operating points.

## Latest results (2026-06-14)

**Categorization:** 0.767 top-1 (23/30). Misses are mostly Hindi/Hinglish complaints
(prototypes are English — a known cross-lingual gap) and a few English near-misses
(e.g. "massive crater" → Road damage vs Pothole). This is *fine*: officials correct
the category at triage, and every correction is logged to the `corrections` table —
the labeled dataset that lets a supervised classifier replace zero-shot later.

**Duplicate detection (threshold sweep):**

| threshold | precision | recall | F1 |
|-----------|-----------|--------|-----|
| 0.55 | 0.688 | 0.846 | 0.759 |
| 0.60 | 0.833 | 0.769 | 0.800 |
| 0.65 | **1.000** | 0.692 | 0.818 |
| 0.78 | 1.000 | 0.462 | 0.632 |
| 0.88 | 1.000 | 0.000 | 0.000 |

## Why the thresholds are what they are

The build plan guessed 0.78 / 0.88 (sensible for the e5 family). **This eval caught
that they're wrong for this model** — at 0.88 auto-attach never fires (recall 0.0). The
paraphrase-MiniLM model scores true duplicates lower, so we calibrated from the data:

- **auto-attach = 0.65** — no human in the loop, so precision must be ~1.0. At 0.65,
  precision is 1.000 (zero false merges on the eval set), recall 0.692.
- **similar-check = 0.60** — only *suggests* to the citizen, who decides; favor recall
  (0.769) so fewer real duplicates slip through. The occasional near-miss is harmless.

These live in `backend/app/core/config.py`. The lesson: **never ship a similarity
threshold you picked by intuition — measure it.** Re-run this whenever the model or
dataset changes.

## Caveats

- 30 categorization examples + 9 duplicate groups is small — numbers are indicative,
  not production-grade. Grow the set as real complaints arrive.
- Pairs are text-only here; the live system also requires same-category + within-150 m,
  which raises real-world precision further.
