"""Блокирующие операции над изображениями и PDF (вызываются через asyncio.to_thread)."""

import base64
import io
import logging

from PIL import Image
from pypdf import PdfReader

logger = logging.getLogger(__name__)


def image_to_png_base64(data: bytes) -> str:
    """Конвертирует изображение любого поддерживаемого формата в PNG (base64)."""
    with Image.open(io.BytesIO(data)) as image:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def is_pdf_scanned(data: bytes, min_text_length: int) -> bool:
    """True, если в PDF нет текстового слоя (скан) или файл не читается."""
    try:
        reader = PdfReader(io.BytesIO(data))
        text_length = 0
        for page in reader.pages:
            text_length += len((page.extract_text() or "").strip())
            if text_length >= min_text_length:
                return False
    except Exception:
        logger.exception("Не удалось проверить PDF на наличие текста, считаем его сканом")
    return True
