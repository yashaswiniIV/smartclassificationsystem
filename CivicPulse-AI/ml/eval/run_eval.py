"""CivicPulse AI — offline evaluation of the AI spine.

Measures two things on a hand-labeled set (ml/eval/dataset.json):
  1. Category top-1 accuracy (zero-shot: complaint embedding vs category prototypes).
  2. Duplicate detection precision/recall/F1 at the configured thresholds.

Fully offline — only needs the embedding model (fastembed). No DB, no API key.
Run from the backend venv:  uv run python ../ml/eval/run_eval.py
"""

import itertools
import json
import sys
from pathlib import Path

# Make the backend package importable so we reuse the EXACT embedding + category
# descriptions the app uses (single source of truth, no drift).
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai.embeddings import embed_texts  # noqa: E402
from scripts.seed import DESCRIPTIONS  # noqa: E402

SIMILAR_CHECK = 0.78  # show as possible duplicate
AUTO_ATTACH = 0.88  # auto-merge without a human


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def eval_categorization(examples: list[dict]) -> None:
    names = list(DESCRIPTIONS)
    # Prototype text = "Name. Description" — the name itself carries strong signal.
    prototypes = dict(
        zip(names, embed_texts([f"{n}. {DESCRIPTIONS[n]}" for n in names]), strict=True)
    )
    vecs = embed_texts([e["text"] for e in examples])

    correct = 0
    misses: list[tuple[str, str, str]] = []
    for ex, v in zip(examples, vecs, strict=True):
        best = max(names, key=lambda n: _cosine(v, prototypes[n]))
        if best == ex["category"]:
            correct += 1
        else:
            misses.append((ex["text"][:50], ex["category"], best))

    n = len(examples)
    print("\n=== Categorization (zero-shot top-1) ===")
    print(f"accuracy: {correct}/{n} = {correct / n:.3f}")
    if misses:
        print("misses (text | expected | predicted):")
        for text, exp, pred in misses:
            print(f"  - {text!r}  exp={exp}  pred={pred}")


def eval_dedup(groups: list[list[str]]) -> None:
    # Flatten with a group id per text; positive pair = same group.
    texts, labels = [], []
    for gid, group in enumerate(groups):
        for t in group:
            texts.append(t)
            labels.append(gid)
    vecs = embed_texts(texts)

    pairs = [
        (labels[i] == labels[j], _cosine(vecs[i], vecs[j]))
        for i, j in itertools.combinations(range(len(texts)), 2)
    ]

    def metrics(threshold: float) -> tuple[float, float, float, int, int, int, int]:
        tp = fp = fn = tn = 0
        for same, sim in pairs:
            predicted = sim >= threshold
            if same and predicted:
                tp += 1
            elif same and not predicted:
                fn += 1
            elif not same and predicted:
                fp += 1
            else:
                tn += 1
        p = tp / (tp + fp) if (tp + fp) else 1.0
        r = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f1, tp, fp, fn, tn

    print("\n=== Duplicate detection (threshold sweep) ===")
    print(f"{'thr':>5}  {'prec':>5}  {'recall':>6}  {'f1':>5}   tp/fp/fn/tn")
    for thr in [0.50, 0.55, 0.60, 0.62, 0.65, 0.70, 0.75, 0.78, 0.88]:
        p, r, f1, tp, fp, fn, tn = metrics(thr)
        print(f"{thr:>5.2f}  {p:>5.3f}  {r:>6.3f}  {f1:>5.3f}   {tp}/{fp}/{fn}/{tn}")

    print("\n=== Configured operating points ===")
    for label, threshold in [("similar-check", SIMILAR_CHECK), ("auto-attach", AUTO_ATTACH)]:
        p, r, f1, tp, fp, fn, tn = metrics(threshold)
        print(
            f"[{label} @ {threshold:.2f}]  precision={p:.3f}  recall={r:.3f}  f1={f1:.3f}"
        )


def main() -> None:
    data = json.loads((Path(__file__).parent / "dataset.json").read_text(encoding="utf-8"))
    print(f"Embedding model: paraphrase-multilingual-MiniLM-L12-v2 (loading…)")
    eval_categorization(data["categorization"])
    eval_dedup(data["duplicate_groups"])
    print()


if __name__ == "__main__":
    main()
