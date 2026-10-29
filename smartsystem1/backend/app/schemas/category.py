from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: int
    name: str
    department_id: int
    severity_weight: int
    sla_hours: int
