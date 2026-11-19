"""Клиент Docling Serve (асинхронный API с опросом статуса задачи)."""

import asyncio
import logging
import time

import httpx

from app.clients.base import is_healthy
from app.core.exceptions import UpstreamServiceError, UpstreamTimeoutError

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = {"success", "completed", "finished"}
FAILURE_STATUSES = {"failed", "error"}
CONVERT_PARAMS = {
    "to_formats": ["md", "text"],
    "image_export_mode": "placeholder",
    "do_ocr": "false",
    "force_ocr": "false",
    "pdf_backend": "pypdfium2",
    "include_images": "false",
    "abort_on_error": "true",
}


class DoclingClient:
    def __init__(self, http: httpx.AsyncClient, base_url: str, timeout: float, poll_interval: float) -> None:
        self._http = http
        self._base_url = base_url
        self._timeout = timeout
        self._poll_interval = poll_interval

    async def convert_to_markdown(self, data: bytes, filename: str, mime_type: str) -> str:
        """Отправляет файл в Docling, ждёт завершения задачи и возвращает markdown."""
        task_id = await self._submit(data, filename, mime_type)
        logger.info("Ожидание обработки %s в Docling, task_id=%s", filename, task_id)
        await self._wait(task_id, filename)
        return await self._result(task_id, filename)

    async def _submit(self, data: bytes, filename: str, mime_type: str) -> str:
        try:
            response = await self._http.post(
                f"{self._base_url}/v1/convert/file/async",
                params=CONVERT_PARAMS,
                files={"files": (filename, data, mime_type)},
                timeout=self._timeout,
            )
            response.raise_for_status()
            task_id = response.json().get("task_id")
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(f"Docling отклонил файл: {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"Docling недоступен: {exc!r}") from exc
        if not task_id:
            raise UpstreamServiceError("Docling не вернул task_id")
        return str(task_id)

    async def _wait(self, task_id: str, filename: str) -> None:
        deadline = time.monotonic() + self._timeout
        last_status: str | None = None
        polls = 0
        while time.monotonic() < deadline:
            await asyncio.sleep(self._poll_interval)
            polls += 1
            try:
                response = await self._http.get(f"{self._base_url}/v1/status/poll/{task_id}", timeout=30.0)
                response.raise_for_status()
                status_data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Ошибка опроса статуса задачи %s: %r", task_id, exc)
                continue

            current = status_data.get("task_status")
            if current != last_status or polls % 3 == 0:
                logger.info("Статус обработки %s: %s", filename, current)
                last_status = current
            if current in SUCCESS_STATUSES:
                return
            if current in FAILURE_STATUSES:
                raise UpstreamServiceError(
                    f"Docling завершил обработку с ошибкой: {status_data.get('error', 'неизвестная ошибка')}"
                )
        raise UpstreamTimeoutError(f"Docling не завершил обработку {filename} за {self._timeout:.0f} с")

    async def _result(self, task_id: str, filename: str) -> str:
        try:
            response = await self._http.get(f"{self._base_url}/v1/result/{task_id}", timeout=self._timeout)
            response.raise_for_status()
            text = response.json().get("document", {}).get("md_content", "")
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamServiceError(f"Не удалось получить результат Docling: {exc!r}") from exc
        if not text:
            logger.warning("Docling вернул пустой текст для %s", filename)
        return str(text)

    async def is_healthy(self) -> bool:
        return await is_healthy(self._http, f"{self._base_url}/health")
