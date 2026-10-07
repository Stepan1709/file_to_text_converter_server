"""
Микросервис конвертации файлов в текст.

Маршрутизирует файлы между внешними сервисами:
- изображения            -> vLLM (PaddleOCR-VL);
- PDF-сканы              -> OCR-сервер (PaddleOCR-VL_pdf_ocr_server);
- PDF с текстом и прочие -> Docling Serve.
"""
import asyncio
import base64
import io
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Optional

import aiohttp
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image
from pypdf import PdfReader

from config import (
    DOC_URL, VLLM_URL, VLLM_API_KEY, OCR_URL, MODEL_NAME,
    DOCLING_TIMEOUT, DOCLING_POLL_INTERVAL, VLLM_REQUEST_TIMEOUT, OCR_REQUEST_TIMEOUT,
    PDF_MIN_TEXT_LENGTH, HOST, PORT, LOG_LEVEL,
    SUPPORTED_FILE_TYPES, FILE_TYPE_BY_EXTENSION, MIME_TYPES, logger,
)

HEALTH_CHECK_TIMEOUT = aiohttp.ClientTimeout(total=5)
# Markdown-картинки, которые Docling вставляет в текст: ![Image](data:image/png;base64,...)
EMBEDDED_IMAGE_RE = re.compile(r"!\[Image\]\(data:image/[^;]+;base64,([^)]+)\)")
UNICODE_ESCAPE_RE = re.compile(r"/uni([0-9A-Fa-f]{4})")

session: Optional[aiohttp.ClientSession] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global session
    session = aiohttp.ClientSession()
    logger.info(f"Сервер запущен на http://{HOST}:{PORT}")
    logger.info(f"Docling: {DOC_URL}, OCR server: {OCR_URL}, vLLM: {VLLM_URL}, модель: {MODEL_NAME}")
    status = await check_service_health()
    logger.info(f"Статус сервисов: {status}")
    yield
    await session.close()


app = FastAPI(
    title="File Converter Server",
    description="Конвертация файлов в текст через Docling Serve, OCR server и PaddleOCR-VL",
    version="1.1.0",
    lifespan=lifespan,
)


def vllm_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if VLLM_API_KEY:
        headers["Authorization"] = f"Bearer {VLLM_API_KEY}"
    return headers


def convert_unicode_escapes(text: str) -> str:
    """Заменяет последовательности вида /uni042F на соответствующие символы."""
    return UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


async def vllm_ocr_png(png_base64: str) -> str:
    """Распознаёт PNG (base64) через vLLM PaddleOCR-VL. При ошибке бросает исключение."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "OCR:"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png_base64}"}},
            ],
        }],
        "max_tokens": 4096,
        "temperature": 0.1,
        "top_p": 0.95,
    }
    async with session.post(f"{VLLM_URL}/v1/chat/completions", json=payload, headers=vllm_headers(),
                            timeout=aiohttp.ClientTimeout(total=VLLM_REQUEST_TIMEOUT)) as response:
        if response.status != 200:
            raise RuntimeError(f"Ошибка vLLM: {response.status}, {await response.text()}")
        result = await response.json()
    return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


async def clean_images_from_text(text: str, ocr_images: bool = False) -> str:
    """Удаляет встроенные изображения из текста или заменяет их результатом OCR."""
    if not ocr_images:
        return EMBEDDED_IMAGE_RE.sub("", text)

    parts = []
    last_end = 0
    for match in EMBEDDED_IMAGE_RE.finditer(text):
        parts.append(text[last_end:match.start()])
        last_end = match.end()
        try:
            ocr_text = await vllm_ocr_png(match.group(1))
        except Exception as e:
            logger.error(f"Ошибка OCR изображения: {e}")
            continue  # изображение, которое не удалось распознать, просто удаляется
        if ocr_text:
            parts.append(f' Image OCR: "{ocr_text}"')
    parts.append(text[last_end:])
    return "".join(parts)


def is_pdf_scanned(pdf_bytes: bytes) -> bool:
    """Возвращает True, если в PDF нет текстового слоя (скан)."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_length = 0
        for page in reader.pages:
            text_length += len((page.extract_text() or "").strip())
            if text_length >= PDF_MIN_TEXT_LENGTH:
                return False
        return True
    except Exception as e:
        logger.error(f"Ошибка проверки PDF на наличие текста: {e}")
        return True  # при ошибке считаем, что это скан


async def _is_healthy(url: str, headers: Optional[dict] = None) -> bool:
    try:
        async with session.get(url, headers=headers, timeout=HEALTH_CHECK_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


async def check_service_health() -> dict:
    """Проверяет доступность внешних сервисов."""
    auth = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else None
    docling, vllm, ocr = await asyncio.gather(
        _is_healthy(f"{DOC_URL}/health"),
        _is_healthy(f"{VLLM_URL}/health", auth),
        _is_healthy(f"{OCR_URL}/health"),
    )
    return {"docling": docling, "vllm": vllm, "ocr": ocr}


async def process_with_docling(file_bytes: bytes, filename: str, ocr_images: bool = False) -> str:
    """Конвертирует файл в markdown через Docling Serve (асинхронный API с опросом статуса)."""
    params = {
        "to_formats": ["md", "text"],
        "image_export_mode": "placeholder",
        "do_ocr": "false",
        "force_ocr": "false",
        "pdf_backend": "pypdfium2",
        "include_images": "false",
        "abort_on_error": "true",
    }
    mime_type = MIME_TYPES.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")

    form_data = aiohttp.FormData()
    form_data.add_field("files", io.BytesIO(file_bytes), filename=filename, content_type=mime_type)

    async with session.post(f"{DOC_URL}/v1/convert/file/async", params=params, data=form_data) as response:
        if response.status != 200:
            raise RuntimeError(f"Ошибка отправки файла в Docling: {response.status}, {await response.text()}")
        task_id = (await response.json()).get("task_id")
    if not task_id:
        raise RuntimeError("Не получен task_id от Docling")

    logger.info(f"Ожидание завершения обработки файла {filename}, Task ID: {task_id}")
    deadline = time.monotonic() + DOCLING_TIMEOUT
    check_count = 0
    last_status = None

    while time.monotonic() < deadline:
        await asyncio.sleep(DOCLING_POLL_INTERVAL)
        check_count += 1

        try:
            async with session.get(f"{DOC_URL}/v1/status/poll/{task_id}") as status_response:
                if status_response.status != 200:
                    logger.warning(f"Ошибка получения статуса: {status_response.status}")
                    continue
                status_data = await status_response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Сетевая ошибка при проверке статуса: {e}")
            continue

        current_status = status_data.get("task_status")
        # Логируем при изменении статуса и примерно раз в 30 секунд
        if check_count % 3 == 0 or current_status != last_status:
            logger.info(f"Статус обработки {filename}: {current_status}, позиция: {status_data.get('task_position', 0)}")
            last_status = current_status

        if current_status in ("success", "completed", "finished"):
            async with session.get(f"{DOC_URL}/v1/result/{task_id}") as result_response:
                if result_response.status != 200:
                    raise RuntimeError("Не удалось получить результат обработки Docling")
                result_data = await result_response.json()

            text = result_data.get("document", {}).get("md_content", "")
            if not text:
                logger.warning(f"Получен пустой текст для файла {filename}")
            text = await clean_images_from_text(text, ocr_images)
            return convert_unicode_escapes(text)

        if current_status in ("failed", "error"):
            raise RuntimeError(f"Обработка Docling завершилась с ошибкой: {status_data.get('error', 'неизвестная ошибка')}")

    raise TimeoutError(f"Docling не завершил обработку {filename} за {DOCLING_TIMEOUT:.0f} с")


async def process_with_ocr_server(file_bytes: bytes, filename: str) -> str:
    """Отправляет PDF на OCR-сервер."""
    form_data = aiohttp.FormData()
    form_data.add_field("file", io.BytesIO(file_bytes), filename=filename, content_type="application/pdf")

    async with session.post(f"{OCR_URL}/ocr", data=form_data,
                            timeout=aiohttp.ClientTimeout(total=OCR_REQUEST_TIMEOUT)) as response:
        if response.status != 200:
            raise RuntimeError(f"Ошибка OCR-сервера: {response.status}, {await response.text()}")
        return await response.text()


def image_to_png_base64(file_bytes: bytes) -> str:
    """Конвертирует изображение любого поддерживаемого формата в PNG (base64)."""
    with Image.open(io.BytesIO(file_bytes)) as image:
        png_buffer = io.BytesIO()
        image.save(png_buffer, format="PNG")
    return base64.b64encode(png_buffer.getvalue()).decode("utf-8")


async def process_with_vllm_ocr(file_bytes: bytes) -> str:
    """Распознаёт изображение через vLLM PaddleOCR-VL."""
    png_base64 = await asyncio.to_thread(image_to_png_base64, file_bytes)
    return await vllm_ocr_png(png_base64)


async def process_file(file_bytes: bytes, filename: str, file_type: str,
                       force_ocr_pdf: bool = False, ocr_images: bool = False) -> str:
    """Выбирает способ обработки файла по его типу."""
    if file_type == "image":
        logger.info(f"Обработка изображения {filename} через vLLM PaddleOCR-VL")
        return await process_with_vllm_ocr(file_bytes)

    if file_type == "pdf":
        if force_ocr_pdf:
            logger.info(f"Обработка PDF {filename} через OCR server (принудительно)")
            return await process_with_ocr_server(file_bytes, filename)
        if await asyncio.to_thread(is_pdf_scanned, file_bytes):
            logger.info(f"PDF {filename} является сканом, обработка через OCR server")
            return await process_with_ocr_server(file_bytes, filename)
        logger.info(f"PDF {filename} содержит текст, обработка через Docling")
        return await process_with_docling(file_bytes, filename, ocr_images)

    logger.info(f"Обработка файла {filename} (тип: {file_type}) через Docling")
    return await process_with_docling(file_bytes, filename, ocr_images)


def get_file_type(filename: str) -> str:
    """Определяет тип файла по расширению."""
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return FILE_TYPE_BY_EXTENSION.get(ext, ext)


@app.get("/live")
async def liveness():
    """Проверка, что процесс жив (без обращения к внешним сервисам)."""
    return {"status": "alive"}


@app.get("/health")
async def health_check():
    """Проверка доступности внешних сервисов."""
    status = await check_service_health()
    return {"status": "healthy" if all(status.values()) else "degraded", "services": status}


@app.post("/convert")
async def convert_file(
        file: UploadFile = File(...),
        force_ocr__only_pdf: Optional[bool] = Form(False),
        ocr_images_in_file: Optional[bool] = Form(False),
):
    """Конвертирует файл в текст."""
    start_time = time.time()
    filename = file.filename or ""

    file_type = get_file_type(filename)
    if file_type not in SUPPORTED_FILE_TYPES:
        raise HTTPException(status_code=400, detail=f"Файлы типа '{file_type}' не поддерживаются.")

    file_bytes = await file.read()
    logger.info(f"Получен файл: {filename}, тип: {file_type}, размер: {len(file_bytes)} байт")

    # Для изображений параметры не применяются
    is_image = file_type == "image"
    force_ocr_pdf = bool(force_ocr__only_pdf) and not is_image
    ocr_images = bool(ocr_images_in_file) and not is_image
    logger.info(f"Параметры: force_ocr_pdf={force_ocr_pdf}, ocr_images={ocr_images}")

    try:
        text = await process_file(file_bytes, filename, file_type, force_ocr_pdf, ocr_images)
    except Exception as e:
        logger.error(f"Ошибка обработки файла {filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {e}")

    worktime = str(timedelta(seconds=int(time.time() - start_time)))
    logger.info(f"Обработка файла {filename} завершена за {worktime}")
    return {"filename": filename, "file_text": text, "worktime": worktime}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
