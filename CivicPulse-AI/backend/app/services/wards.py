import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def import_feature_collection(
    db: AsyncSession,
    fc: dict[str, Any],
    *,
    code_prop: str,
    name_prop: str,
    zone_prop: str | None = None,
) -> int:
    """Upsert wards from a GeoJSON FeatureCollection. Idempotent on ward_code, so
    re-running (or re-importing corrected boundaries) is safe. Polygons are coerced
    to MultiPolygon to match the column type."""
    features = fc.get("features", [])
    count = 0
    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry")
        if geom is None or code_prop not in props:
            continue
        await db.execute(
            text(
                """
                INSERT INTO wards (ward_code, name, zone, geom)
                VALUES (
                    :code, :name, :zone,
                    ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geom), 4326))
                )
                ON CONFLICT (ward_code)
                DO UPDATE SET name = EXCLUDED.name, zone = EXCLUDED.zone, geom = EXCLUDED.geom
                """
            ),
            {
                "code": str(props[code_prop]),
                "name": str(props.get(name_prop, props[code_prop])),
                "zone": str(props[zone_prop]) if zone_prop and props.get(zone_prop) else None,
                "geom": json.dumps(geom),
            },
        )
        count += 1
    await db.commit()
    return count
