"""Зависимости FastAPI: доступ к объектам, созданным в lifespan."""

from typing import Annotated

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.services.converter import ConverterService


def get_converter(request: Request) -> ConverterService:
    converter: ConverterService = request.app.state.converter
    return converter


SettingsDep = Annotated[Settings, Depends(get_settings)]
ConverterDep = Annotated[ConverterService, Depends(get_converter)]
