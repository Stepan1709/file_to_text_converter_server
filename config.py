import logging
from secrets import DOC_URL, VLLM_URL, VLLM_API_KEY, OCR_URL, MODEL_NAME

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Проверка импорта и замена на localhost при необходимости
try:
    from secrets import DOC_URL
except ImportError:
    DOC_URL = "http://localhost:9001"
    logger.warning("Не удалось импортировать DOC_URL, использую localhost")

try:
    from secrets import VLLM_URL
except ImportError:
    VLLM_URL = "http://localhost:8400"
    logger.warning("Не удалось импортировать VLLM_URL, использую localhost")

try:
    from secrets import VLLM_API_KEY
except ImportError:
    VLLM_API_KEY = ""
    logger.warning("Не удалось импортировать VLLM_API_KEY, оставляю пустым")

try:
    from secrets import OCR_URL
except ImportError:
    OCR_URL = "http://localhost:9000"
    logger.warning("Не удалось импортировать OCR_URL, использую localhost")

try:
    from secrets import MODEL_NAME
except ImportError:
    MODEL_NAME = "PaddlePaddle/PaddleOCR-VL"
    logger.warning("Не удалось импортировать MODEL_NAME, использую значение по умолчанию")

# Конфигурация сервера
HOST = "0.0.0.0"
PORT = 8999

# Поддерживаемые типы файлов
SUPPORTED_FILE_TYPES = [
    "docx", "pptx", "html", "image", "pdf",
    "md", "csv", "xlsx", "xml_uspto", "xml_jats", "json_docling"
]

# MIME типы для различных расширений
MIME_TYPES = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.html': 'text/html',
    '.md': 'text/markdown',
    '.csv': 'text/csv',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.txt': 'text/plain',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.bmp': 'image/bmp'
}