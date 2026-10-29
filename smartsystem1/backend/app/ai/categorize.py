"""Zero-shot categorization: compare a complaint's embedding to each category's
prototype embedding (built from the category description). No labeled training
data required — that's the point. The LLM is only a low-confidence fallback.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embeddings, llm
from app.core.config import get_settings
from app.models.org import Category

settings = get_settings()


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


async def ensure_category_embeddings(db: AsyncSession) -> int:
    """Populate categories.embedding for any category missing one. Idempotent."""
    cats = (await db.execute(select(Category).where(Category.embedding.is_(None)))).scalars().all()
    if not cats:
        return 0
    # Prototype text = "Name. Description" (the name carries strong signal too).
    vectors = await asyncio.to_thread(
        embeddings.embed_passages, [f"{c.name}. {c.description}" for c in cats]
    )
    for cat, vec in zip(cats, vectors, strict=True):
        cat.embedding = vec
    await db.commit()
    return len(cats)


async def categorize(
    db: AsyncSession, complaint_embedding: list[float], description: str
) -> tuple[int | None, float]:
    """Return (category_id, confidence). Embedding similarity first; if it's weak
    and a real LLM is configured, ask it for a second opinion."""
    rows = (
        await db.execute(
            select(Category.id, Category.name, Category.embedding).where(
                Category.embedding.is_not(None)
            )
        )
    ).all()
    if not rows:
        return None, 0.0

    best_id, best_sim = None, -1.0
    for cat_id, _name, emb in rows:
        sim = _cosine(complaint_embedding, list(emb))
        if sim > best_sim:
            best_id, best_sim = cat_id, sim

    if best_sim >= settings.category_confidence_min:
        return best_id, round(best_sim, 4)

    # Low confidence — let the LLM (if available) take a look.
    llm_choice = await llm.classify(description, [(cid, name) for cid, name, _ in rows])
    if llm_choice is not None:
        return llm_choice
    return best_id, round(max(best_sim, 0.0), 4)
