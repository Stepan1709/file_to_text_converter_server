"""Служебные эндпоинты: liveness и health."""

from fastapi import APIRouter

from app.api.deps import ConverterDep
from app.schemas.health import HealthResponse, LiveResponse

router = APIRouter(tags=["service"])


@router.get("/live", response_model=LiveResponse)
async def liveness() -> LiveResponse:
    """Проверка, что процесс жив (без обращения к внешним сервисам)."""
    return LiveResponse(status="alive")


@router.get("/health", response_model=HealthResponse)
async def health(converter: ConverterDep) -> HealthResponse:
    """Проверка доступности внешних сервисов."""
    services = await converter.check_services()
    return HealthResponse(status="healthy" if all(services.values()) else "degraded", services=services)
