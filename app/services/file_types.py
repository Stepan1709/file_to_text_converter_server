"""Определение типа файла по расширению."""

import os

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
    "docx",
    "pptx",
    "html",
    "image",
    "pdf",
    "md",
    "csv",
    "xlsx",
    "xml_uspto",
    "xml_jats",
    "json_docling",
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


def get_file_type(filename: str) -> str:
    """Определяет тип обработки по расширению файла."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return FILE_TYPE_BY_EXTENSION.get(ext, ext)


def get_mime_type(filename: str) -> str:
    return MIME_TYPES.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")
