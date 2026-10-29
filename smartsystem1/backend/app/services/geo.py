from geoalchemy2 import WKTElement
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def point(lng: float, lat: float) -> WKTElement:
    """A 4326 point for inserting into geography/geometry columns. GeoJSON order: [lng, lat]."""
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


async def find_ward(db: AsyncSession, lng: float, lat: float) -> int | None:
    """Point-in-polygon: which ward contains this coordinate? None if outside the city."""
    row = (
        await db.execute(
            text(
                "SELECT id FROM wards "
                "WHERE ST_Contains(geom, ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)) "
                "ORDER BY id LIMIT 1"
            ),
            {"lng": lng, "lat": lat},
        )
    ).first()
    return row[0] if row else None
