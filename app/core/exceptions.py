"""Доменные исключения и их преобразование в HTTP-ответы."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Базовое исключение сервиса."""

    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = "Внутренняя ошибка сервиса"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.detail
        super().__init__(self.detail)


class UnsupportedFileTypeError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST


class EmptyFileError(AppError):
    status_code = status.HTTP_400_BAD_REQUEST
    detail = "Файл пуст"


class FileTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE


class UpstreamServiceError(AppError):
    """Внешний сервис (Docling, vLLM, OCR-сервер) вернул ошибку или недоступен."""

    status_code = status.HTTP_502_BAD_GATEWAY
    detail = "Ошибка внешнего сервиса"


class UpstreamTimeoutError(AppError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    detail = "Внешний сервис не ответил вовремя"


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
