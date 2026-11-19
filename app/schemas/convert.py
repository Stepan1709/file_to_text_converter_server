"""Схемы эндпоинта /convert."""

from pydantic import BaseModel


class ConvertResponse(BaseModel):
    filename: str
    file_text: str
    worktime: str
