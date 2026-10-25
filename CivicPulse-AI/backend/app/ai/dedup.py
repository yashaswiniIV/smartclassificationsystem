"""Duplicate detection: ONE SQL query combining vector similarity (pgvector),
spatial radius (PostGIS), category, and open-status — the query that makes a
separate FAISS index unnecessary at this scale (see ADR-02).
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import embeddings


@dataclass
class SimilarIssue:
    issue_id: str
    public_code: str
    title: str
    status: str
    complaint_count: int
    upvote_count: int
    similarity: float
    distance_m: float


_SQL = text(
    """
    SELECT i.id, i.public_code, i.title, i.status::text AS status,
           i.complaint_count, i.upvote_count,
           1 - MIN(c.embedding <=> (:emb)::vector) AS similarity,
           MIN(ST_Distance(
               c.location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
           )) AS meters
    FROM issues i
    JOIN complaints c ON c.issue_id = i.id
    WHERE i.status NOT IN ('resolved', 'closed', 'rejected')
      AND c.embedding IS NOT NULL
      AND ((:category_id)::int IS NULL OR i.category_id = (:category_id)::int)
      AND ((:exclude_id)::uuid IS NULL OR c.id <> (:exclude_id)::uuid)
      AND ST_DWithin(
          c.location, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography, :radius
      )
    GROUP BY i.id
    HAVING 1 - MIN(c.embedding <=> (:emb)::vector) >= :min_sim
    ORDER BY similarity DESC
    LIMIT :limit
    """
)


async def find_similar_issues(
    db: AsyncSession,
    embedding: list[float],
    lng: float,
    lat: float,
    *,
    radius_m: int,
    min_sim: float,
    category_id: int | None = None,
    exclude_complaint_id: str | None = None,
    limit: int = 3,
) -> list[SimilarIssue]:
    rows = (
        await db.execute(
            _SQL,
            {
                "emb": embeddings.to_pgvector(embedding),
                "lng": lng,
                "lat": lat,
                "radius": radius_m,
                "min_sim": min_sim,
                "category_id": category_id,
                "exclude_id": exclude_complaint_id,
                "limit": limit,
            },
        )
    ).mappings()
    return [
        SimilarIssue(
            issue_id=str(r["id"]),
            public_code=r["public_code"],
            title=r["title"],
            status=r["status"],
            complaint_count=r["complaint_count"],
            upvote_count=r["upvote_count"],
            similarity=round(float(r["similarity"]), 4),
            distance_m=round(float(r["meters"]), 1),
        )
        for r in rows
    ]
