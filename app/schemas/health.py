"""Схемы служебных эндпоинтов."""

from pydantic import BaseModel


class LiveResponse(BaseModel):
    status: str


class HealthResponse(BaseModel):
    status: str
    services: dict[str, bool]
