"""Эндпоинт конвертации файла в текст."""

import logging
import time
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.deps import ConverterDep, SettingsDep
from app.core.exceptions import EmptyFileError, FileTooLargeError
from app.schemas.convert import ConvertResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["convert"])


@router.post("/convert", response_model=ConvertResponse)
async def convert_file(
    converter: ConverterDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    force_ocr__only_pdf: Annotated[bool, Form()] = False,
    ocr_images_in_file: Annotated[bool, Form()] = False,
) -> ConvertResponse:
    """Конвертирует файл в текст."""
    started = time.monotonic()
    filename = file.filename or ""

    limit = settings.max_upload_size_bytes
    data = await file.read(limit + 1)
    if not data:
        raise EmptyFileError()
    if len(data) > limit:
        raise FileTooLargeError(f"Файл больше {settings.max_upload_size_mb} МБ")
    logger.info("Получен файл %s, размер: %d байт", filename, len(data))

    text = await converter.convert(
        data, filename, force_ocr_pdf=force_ocr__only_pdf, ocr_images=ocr_images_in_file
    )

    worktime = str(timedelta(seconds=int(time.monotonic() - started)))
    logger.info("Обработка файла %s завершена за %s", filename, worktime)
    return ConvertResponse(filename=filename, file_text=text, worktime=worktime)
