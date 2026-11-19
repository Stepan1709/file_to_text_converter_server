"""Точка входа: сборка FastAPI-приложения."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.api.routers import convert, health
from app.clients.docling import DoclingClient
from app.clients.ocr_server import OcrServerClient
from app.clients.vllm import VllmClient
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.services.converter import ConverterService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    # Таймауты задаются на уровне каждого запроса в клиентах
    async with httpx.AsyncClient(timeout=httpx.Timeout(None, connect=10.0)) as http:
        app.state.converter = ConverterService(
            docling=DoclingClient(
                http, settings.doc_base_url, settings.docling_timeout, settings.docling_poll_interval
            ),
            vllm=VllmClient(
                http,
                settings.vllm_base_url,
                settings.model_name,
                settings.vllm_api_key,
                settings.vllm_request_timeout,
            ),
            ocr_server=OcrServerClient(http, settings.ocr_base_url, settings.ocr_request_timeout),
            pdf_min_text_length=settings.pdf_min_text_length,
        )
        logger.info(
            "Сервис запущен: Docling %s, OCR-сервер %s, vLLM %s (модель %s)",
            settings.doc_base_url,
            settings.ocr_base_url,
            settings.vllm_base_url,
            settings.model_name,
        )
        logger.info("Статус сервисов: %s", await app.state.converter.check_services())
        yield
    logger.info("Сервис остановлен")


def create_app() -> FastAPI:
    setup_logging(get_settings().log_level)
    app = FastAPI(
        title="File Converter Server",
        description="Конвертация файлов в текст через Docling Serve, OCR-сервер и PaddleOCR-VL",
        version="2.0.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(convert.router)
    return app


app = create_app()
