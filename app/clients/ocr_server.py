"""Клиент OCR-сервера для PDF-сканов (PaddleOCR-VL_pdf_ocr_server)."""

import httpx

from app.clients.base import is_healthy
from app.core.exceptions import UpstreamServiceError, UpstreamTimeoutError


class OcrServerClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, timeout: float) -> None:
        self._http = http
        self._base_url = base_url
        self._timeout = timeout

    async def ocr_pdf(self, data: bytes, filename: str) -> str:
        try:
            response = await self._http.post(
                f"{self._base_url}/ocr",
                files={"file": (filename, data, "application/pdf")},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("OCR-сервер не ответил вовремя") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(f"OCR-сервер вернул ошибку {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"OCR-сервер недоступен: {exc!r}") from exc
        return response.text

    async def is_healthy(self) -> bool:
        return await is_healthy(self._http, f"{self._base_url}/health")
