"""Общая часть клиентов внешних сервисов."""

import logging

import httpx

logger = logging.getLogger(__name__)

HEALTH_TIMEOUT = 5.0


async def is_healthy(http: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None) -> bool:
    """True, если GET по адресу вернул 200."""
    try:
        response = await http.get(url, headers=headers, timeout=HEALTH_TIMEOUT)
    except httpx.HTTPError:
        return False
    return response.status_code == 200
