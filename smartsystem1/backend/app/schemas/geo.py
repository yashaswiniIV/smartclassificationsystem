from typing import Literal

from pydantic import BaseModel, field_validator


class GeoPoint(BaseModel):
    """GeoJSON Point. Coordinates are ALWAYS [longitude, latitude] — the most common
    geo bug is swapping them, so it's validated in one place here."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]

    @field_validator("coordinates")
    @classmethod
    def _in_range(cls, v: tuple[float, float]) -> tuple[float, float]:
        lng, lat = v
        if not (-180 <= lng <= 180 and -90 <= lat <= 90):
            raise ValueError("coordinates must be [lng, lat] within valid ranges")
        return v

    @property
    def lng(self) -> float:
        return self.coordinates[0]

    @property
    def lat(self) -> float:
        return self.coordinates[1]
