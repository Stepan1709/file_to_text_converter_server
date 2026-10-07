"""Конфигурация сервиса. Все параметры задаются переменными окружения."""
import logging
import os

DOC_URL = os.getenv("DOC_URL", "http://localhost:9001").rstrip("/")
VLLM_URL = os.getenv("VLLM_URL", "http://localhost:8400").rstrip("/")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "").strip()
OCR_URL = os.getenv("OCR_URL", "http://localhost:9000").rstrip("/")
MODEL_NAME = os.getenv("MODEL_NAME", "PaddlePaddle/PaddleOCR-VL")

DOCLING_TIMEOUT = float(os.getenv("DOCLING_TIMEOUT", "3600"))
DOCLING_POLL_INTERVAL = float(os.getenv("DOCLING_POLL_INTERVAL", "10"))
VLLM_REQUEST_TIMEOUT = float(os.getenv("VLLM_REQUEST_TIMEOUT", "300"))
OCR_REQUEST_TIMEOUT = float(os.getenv("OCR_REQUEST_TIMEOUT", "3600"))
PDF_MIN_TEXT_LENGTH = int(os.getenv("PDF_MIN_TEXT_LENGTH", "100"))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8999"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("file_converter")

# Расширение файла -> тип обработки
FILE_TYPE_BY_EXTENSION = {
    "docx": "docx",
    "pptx": "pptx",
    "html": "html",
    "htm": "html",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "bmp": "image",
    "tiff": "image",
    "pdf": "pdf",
    "md": "md",
    "csv": "csv",
    "xlsx": "xlsx",
    "xml": "xml_uspto",  # по умолчанию считаем xml_uspto
    "json": "json_docling",
}

SUPPORTED_FILE_TYPES = {
    "docx", "pptx", "html", "image", "pdf",
    "md", "csv", "xlsx", "xml_uspto", "xml_jats", "json_docling",
}

# MIME-типы для передачи файлов в Docling
MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".html": "text/html",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}
