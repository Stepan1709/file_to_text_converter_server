import asyncio
import base64
import io
import os
import re
import time
from datetime import timedelta
from typing import Optional
from pathlib import Path
import tempfile

import aiohttp
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
import uvicorn
from PIL import Image
import PyPDF2
from pdf2image import convert_from_bytes

from config import (
    DOC_URL, VLLM_URL, VLLM_API_KEY, OCR_URL, MODEL_NAME,
    HOST, PORT, SUPPORTED_FILE_TYPES, MIME_TYPES, logger
)

# Создаем FastAPI приложение
app = FastAPI(
    title="File Converter Server",
    description="Сервер для конвертации всех типов файлов с помощью Docling serve, OCR server и PaddleOCR-VL"
)

# Состояние доступности сервисов
service_status = {
    "docling": False,
    "vllm": False,
    "ocr": False
}


def convert_unicode_escapes(text: str) -> str:
    """
    Заменяет структуры типа /uni042F на соответствующие символы
    """

    def replace_unicode(match):
        code = match.group(1)
        try:
            # Преобразуем шестнадцатеричный код в символ
            return chr(int(code, 16))
        except (ValueError, OverflowError):
            return match.group(0)

    # Ищем паттерн /uniXXXX где XXXX - шестнадцатеричный код
    pattern = r'/uni([0-9A-Fa-f]{4})'
    return re.sub(pattern, replace_unicode, text)


def clean_images_from_text(text: str, ocr_images: bool = False, session: aiohttp.ClientSession = None) -> str:
    """
    Удаляет или заменяет изображения в тексте на их OCR результат
    """
    # Паттерн для поиска изображений в формате ![Image](data:image/png;base64,...)
    pattern = r'!\[Image\]\(data:image/[^;]+;base64,[^)]+\)'

    if not ocr_images:
        # Просто удаляем все изображения
        return re.sub(pattern, '', text)

    # Асинхронная обработка изображений
    async def process_image_async(match, session):
        image_data = match.group(0)
        # Извлекаем base64 данные
        base64_match = re.search(r'data:image/[^;]+;base64,([^)]+)', image_data)
        if not base64_match:
            return ''

        image_base64 = base64_match.group(1)

        try:
            # Декодируем base64 в байты
            image_bytes = base64.b64decode(image_base64)

            # Отправляем на OCR в vLLM
            payload = {
                "model": MODEL_NAME,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "OCR:"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 4096,
                "temperature": 0.1,
                "top_p": 0.95
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {VLLM_API_KEY}"
            }

            async with session.post(f"{VLLM_URL}/v1/chat/completions", json=payload, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    ocr_text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    if ocr_text:
                        return f"\n Image OCR: \"{ocr_text}\"\n"

        except Exception as e:
            logger.error(f"Ошибка OCR изображения: {e}")

        # Если OCR не удался или текст пустой, удаляем изображение
        return ''

    # Создаем синхронную обертку для асинхронной функции
    async def process_all_images(text, session):
        matches = list(re.finditer(pattern, text))
        if not matches:
            return text

        # Обрабатываем изображения последовательно
        result_text = text
        offset = 0
        for match in matches:
            replacement = await process_image_async(match, session)
            start, end = match.span()
            result_text = result_text[:start + offset] + replacement + result_text[end + offset:]
            offset += len(replacement) - (end - start)

        return result_text

    # Запускаем асинхронную обработку в синхронном контексте
    # Это будет вызвано из асинхронной функции, поэтому возвращаем coroutine
    return process_all_images(text, session) if session else text


def is_pdf_scanned(pdf_bytes: bytes) -> bool:
    """
    Проверяет, является ли PDF сканом документа (не содержит текста)
    """
    try:
        # Пытаемся извлечь текст из PDF
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text += page_text

        # Если извлечено более 100 символов текста, считаем, что текст есть
        return len(text.strip()) < 100
    except Exception as e:
        logger.error(f"Ошибка проверки PDF на наличие текста: {e}")
        return True  # При ошибке считаем, что это скан


async def check_service_health() -> dict:
    """
    Проверяет доступность всех внешних сервисов
    """
    status = {}

    # Проверка Docling
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{DOC_URL}/health", timeout=5) as resp:
                status['docling'] = resp.status == 200
    except:
        status['docling'] = False

    # Проверка vLLM
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {VLLM_API_KEY}"} if VLLM_API_KEY else {}
            async with session.get(f"{VLLM_URL}/health", headers=headers, timeout=5) as resp:
                status['vllm'] = resp.status == 200
    except:
        status['vllm'] = False

    # Проверка OCR server
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OCR_URL}/health", timeout=5) as resp:
                status['ocr'] = resp.status == 200
    except:
        status['ocr'] = False

    return status


async def process_with_docling(file_bytes: bytes, filename: str, ocr_images: bool = False) -> str:
    """
    Обрабатывает файл через Docling serve
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Параметры запроса
            params = {
                "to_formats": ["md", "text"],
                "image_export_mode": "placeholder",
                "do_ocr": "false",
                "force_ocr": "false",
                "pdf_backend": "pypdfium2",
                "include_images": "false",
                "abort_on_error": "true"
            }

            # Определяем расширение и MIME тип
            file_extension = os.path.splitext(filename)[1].lower()
            mime_type = MIME_TYPES.get(file_extension, 'application/octet-stream')

            # Создаем FormData
            form_data = aiohttp.FormData()
            form_data.add_field(
                'files',
                io.BytesIO(file_bytes),
                filename=filename,
                content_type=mime_type
            )

            # Отправляем на асинхронную обработку
            async with session.post(
                    f"{DOC_URL}/v1/convert/file/async",
                    params=params,
                    data=form_data
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка отправки файла в Docling: {response.status}")

                result = await response.json()
                task_id = result.get('task_id')

                # Ожидаем завершения обработки
                logger.info(f"Ожидание завершения обработки файла {filename}, Task ID: {task_id}")

                check_count = 0
                while True:
                    await asyncio.sleep(10)
                    check_count += 1

                    # Получаем статус задачи
                    async with session.get(f"{DOC_URL}/v1/status/poll/{task_id}") as status_response:
                        if status_response.status != 200:
                            continue

                        status_data = await status_response.json()
                        current_status = status_data.get('task_status')

                        # Логируем каждую третью проверку (30 секунд)
                        if check_count % 3 == 0:
                            position = status_data.get('task_position', 0)
                            logger.info(f"Статус обработки {filename}: {current_status}, позиция: {position}")

                        if current_status in ['success', 'completed', 'finished']:
                            # Получаем результат
                            async with session.get(f"{DOC_URL}/v1/result/{task_id}") as result_response:
                                if result_response.status != 200:
                                    raise Exception("Не удалось получить результат обработки")

                                result_data = await result_response.json()
                                # Извлекаем текст из document.md_content
                                text = result_data.get('document', {}).get('md_content', '')

                                # Очищаем текст от изображений
                                text = await clean_images_from_text(text, ocr_images, session)

                                # Конвертируем Unicode escape последовательности
                                text = convert_unicode_escapes(text)

                                return text
    except Exception as e:
        logger.error(f"Ошибка обработки через Docling: {e}")
        raise


async def process_with_ocr_server(file_bytes: bytes, filename: str) -> str:
    """
    Обрабатывает файл через OCR server
    """
    try:
        async with aiohttp.ClientSession() as session:
            # Создаем FormData
            form_data = aiohttp.FormData()
            form_data.add_field(
                'file',
                io.BytesIO(file_bytes),
                filename=filename
            )

            # Отправляем на OCR
            async with session.post(f"{OCR_URL}/ocr", data=form_data) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка OCR обработки: {response.status}")

                result = await response.text()
                return result
    except Exception as e:
        logger.error(f"Ошибка обработки через OCR server: {e}")
        raise


async def process_with_vllm_ocr(file_bytes: bytes, filename: str) -> str:
    """
    Обрабатывает изображение через vLLM PaddleOCR-VL
    """
    try:
        # Конвертируем в PNG если нужно
        image = Image.open(io.BytesIO(file_bytes))

        # Сохраняем в PNG в памяти
        png_buffer = io.BytesIO()
        image.save(png_buffer, format='PNG')
        png_bytes = png_buffer.getvalue()

        # Кодируем в base64
        image_base64 = base64.b64encode(png_bytes).decode('utf-8')
        image_url = f"data:image/png;base64,{image_base64}"

        # Формируем запрос к vLLM
        payload = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "OCR:"
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.1,
            "top_p": 0.95
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {VLLM_API_KEY}"
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                    f"{VLLM_URL}/v1/chat/completions",
                    json=payload,
                    headers=headers
            ) as response:
                if response.status != 200:
                    raise Exception(f"Ошибка vLLM обработки: {response.status}")

                result = await response.json()
                text = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                return text
    except Exception as e:
        logger.error(f"Ошибка обработки изображения через vLLM: {e}")
        return ""  # Возвращаем пустую строку при ошибке


async def process_file(file_bytes: bytes, filename: str, file_type: str,
                       force_ocr_pdf: bool = False, ocr_images: bool = False) -> str:
    """
    Основная функция обработки файла
    """
    # Для image файлов
    if file_type == "image":
        logger.info(f"Обработка изображения {filename} через vLLM PaddleOCR-VL")
        return await process_with_vllm_ocr(file_bytes, filename)

    # Для PDF файлов
    if file_type == "pdf":
        if force_ocr_pdf:
            logger.info(f"Обработка PDF {filename} через OCR server (принудительно)")
            return await process_with_ocr_server(file_bytes, filename)
        else:
            # Проверяем, содержит ли PDF текст
            if is_pdf_scanned(file_bytes):
                logger.info(f"PDF {filename} является сканом, обработка через OCR server")
                return await process_with_ocr_server(file_bytes, filename)
            else:
                logger.info(f"PDF {filename} содержит текст, обработка через Docling")
                return await process_with_docling(file_bytes, filename, ocr_images)

    # Для остальных типов файлов
    logger.info(f"Обработка файла {filename} (тип: {file_type}) через Docling")
    return await process_with_docling(file_bytes, filename, ocr_images)


def get_file_type(filename: str) -> str:
    """
    Определяет тип файла по расширению
    """
    ext = os.path.splitext(filename)[1].lower().lstrip('.')

    # Маппинг расширений на типы
    type_mapping = {
        'docx': 'docx',
        'pptx': 'pptx',
        'html': 'html',
        'htm': 'html',
        'png': 'image',
        'jpg': 'image',
        'jpeg': 'image',
        'gif': 'image',
        'bmp': 'image',
        'tiff': 'image',
        'pdf': 'pdf',
        'md': 'md',
        'csv': 'csv',
        'xlsx': 'xlsx',
        'xml': 'xml_uspto',  # По умолчанию считаем xml_uspto
        'json': 'json_docling'
    }

    return type_mapping.get(ext, ext)


@app.on_event("startup")
async def startup_event():
    """
    Проверяет доступность сервисов при запуске
    """
    global service_status
    logger.info(f"🚀 Сервер запущен на http://{HOST}:{PORT}")
    logger.info(f"📡 Подключен к Docling: {DOC_URL}")
    logger.info(f"📡 Подключен к OCR server: {OCR_URL}")
    logger.info(f"📡 Подключен к vLLM: {VLLM_URL}")
    logger.info(f"🤖 Модель: {MODEL_NAME}")

    # Проверяем доступность сервисов
    service_status = await check_service_health()
    logger.info(f"Статус сервисов: Docling: {service_status['docling']}, "
                f"vLLM: {service_status['vllm']}, OCR: {service_status['ocr']}")


@app.get("/health")
async def health_check():
    """
    Проверка здоровья сервиса и доступности внешних сервисов
    """
    status = await check_service_health()
    all_healthy = all(status.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "services": status
    }


@app.get("/docs")
async def get_api_info():
    """
    Возвращает описание API из файла api_info.txt
    """
    try:
        with open("api_info.txt", "r", encoding="utf-8") as f:
            info_text = f.read()
        return JSONResponse(content={"api_info": info_text})
    except Exception as e:
        logger.error(f"Ошибка чтения api_info.txt: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Не удалось загрузить описание API"}
        )


@app.post("/convert")
async def convert_file(
        file: UploadFile = File(...),
        force_ocr__only_pdf: Optional[bool] = Form(False),
        ocr_images_in_file: Optional[bool] = Form(False)
):
    """
    Конвертирует файл в текст
    """
    start_time = time.time()

    try:
        # Определяем тип файла
        file_type = get_file_type(file.filename)

        # Проверяем поддержку типа файла
        if file_type not in SUPPORTED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Файлы типа {file_type} не поддерживаются."
            )

        # Читаем содержимое файла
        file_bytes = await file.read()

        # Логируем начало обработки
        logger.info(f"Получен файл: {file.filename}, тип: {file_type}, "
                    f"размер: {len(file_bytes)} байт")

        # Для image файлов игнорируем параметры
        if file_type == "image":
            force_ocr_pdf_effective = False
            ocr_images_effective = False
            logger.info(f"Обработка изображения через vLLM PaddleOCR-VL")
        else:
            force_ocr_pdf_effective = force_ocr__only_pdf
            ocr_images_effective = ocr_images_in_file
            logger.info(f"Параметры: force_ocr_pdf={force_ocr_pdf_effective}, "
                        f"ocr_images={ocr_images_effective}")

        # Обрабатываем файл
        text = await process_file(
            file_bytes,
            file.filename,
            file_type,
            force_ocr_pdf_effective,
            ocr_images_effective
        )

        # Вычисляем время обработки
        end_time = time.time()
        worktime_seconds = end_time - start_time
        worktime = str(timedelta(seconds=int(worktime_seconds)))

        logger.info(f"Обработка файла {file.filename} завершена за {worktime}")

        return {
            "filename": file.filename,
            "file_text": text,
            "worktime": worktime
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка обработки файла {file.filename}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)