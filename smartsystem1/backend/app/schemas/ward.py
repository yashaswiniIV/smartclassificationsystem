from typing import Any

from pydantic import BaseModel


class WardOut(BaseModel):
    id: int
    ward_code: str
    name: str
    zone: str | None


class WardImportRequest(BaseModel):
    code_prop: str = "KGISWardCode"
    name_prop: str = "KGISWardName"
    zone_prop: str | None = None
    feature_collection: dict[str, Any]


class WardImportResult(BaseModel):
    imported: int
