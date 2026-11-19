"""Сценарий конвертации: выбор внешнего сервиса по типу файла."""

import asyncio
import logging

from app.clients.docling import DoclingClient
from app.clients.ocr_server import OcrServerClient
from app.clients.vllm import VllmClient
from app.core.exceptions import AppError, UnsupportedFileTypeError
from app.services.file_types import SUPPORTED_FILE_TYPES, get_file_type, get_mime_type
from app.services.media import image_to_png_base64, is_pdf_scanned
from app.services.text_cleaning import (
    convert_unicode_escapes,
    remove_embedded_images,
    replace_images_with_ocr,
)

logger = logging.getLogger(__name__)


class ConverterService:
    def __init__(
        self,
        docling: DoclingClient,
        vllm: VllmClient,
        ocr_server: OcrServerClient,
        pdf_min_text_length: int,
    ) -> None:
        self._docling = docling
        self._vllm = vllm
        self._ocr_server = ocr_server
        self._pdf_min_text_length = pdf_min_text_length

    async def convert(
        self, data: bytes, filename: str, force_ocr_pdf: bool = False, ocr_images: bool = False
    ) -> str:
        """Конвертирует файл в текст. Для изображений флаги force_ocr_pdf и ocr_images не применяются."""
        file_type = get_file_type(filename)
        if file_type not in SUPPORTED_FILE_TYPES:
            raise UnsupportedFileTypeError(f"Файлы типа '{file_type}' не поддерживаются.")

        if file_type == "image":
            logger.info("Обработка изображения %s через vLLM PaddleOCR-VL", filename)
            png_base64 = await asyncio.to_thread(image_to_png_base64, data)
            return await self._vllm.ocr_png(png_base64)

        if file_type == "pdf":
            if force_ocr_pdf:
                logger.info("PDF %s: принудительный OCR", filename)
                return await self._ocr_server.ocr_pdf(data, filename)
            if await asyncio.to_thread(is_pdf_scanned, data, self._pdf_min_text_length):
                logger.info("PDF %s является сканом, обработка через OCR-сервер", filename)
                return await self._ocr_server.ocr_pdf(data, filename)

        logger.info("Обработка %s (тип: %s) через Docling", filename, file_type)
        text = await self._docling.convert_to_markdown(data, filename, get_mime_type(filename))
        if ocr_images:
            text = await replace_images_with_ocr(text, self._try_ocr_image)
        else:
            text = remove_embedded_images(text)
        return convert_unicode_escapes(text)

    async def _try_ocr_image(self, png_base64: str) -> str | None:
        try:
            return await self._vllm.ocr_png(png_base64)
        except AppError as exc:
            logger.error("Ошибка OCR изображения: %s", exc.detail)
            return None

    async def check_services(self) -> dict[str, bool]:
        docling, vllm, ocr = await asyncio.gather(
            self._docling.is_healthy(), self._vllm.is_healthy(), self._ocr_server.is_healthy()
        )
        return {"docling": docling, "vllm": vllm, "ocr": ocr}
