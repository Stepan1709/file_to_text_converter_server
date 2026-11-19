"""Клиент vLLM с моделью PaddleOCR-VL (OCR изображений)."""

import httpx

from app.clients.base import is_healthy
from app.core.exceptions import UpstreamServiceError, UpstreamTimeoutError


class VllmClient:
    def __init__(
        self, http: httpx.AsyncClient, base_url: str, model: str, api_key: str, timeout: float
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._model = model
        self._timeout = timeout
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    async def ocr_png(self, png_base64: str) -> str:
        """Распознаёт PNG (base64) и возвращает текст."""
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "OCR:"},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_base64}"}},
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "top_p": 0.95,
        }
        try:
            response = await self._http.post(
                f"{self._base_url}/v1/chat/completions",
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("vLLM не ответил вовремя") from exc
        except httpx.HTTPStatusError as exc:
            raise UpstreamServiceError(f"vLLM вернул ошибку {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"vLLM недоступен: {exc!r}") from exc
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise UpstreamServiceError(f"Некорректный ответ vLLM: {exc!r}") from exc
        return str(content or "").strip()

    async def is_healthy(self) -> bool:
        return await is_healthy(self._http, f"{self._base_url}/health", self._headers or None)
