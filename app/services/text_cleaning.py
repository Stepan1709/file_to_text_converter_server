"""Очистка текста, полученного из Docling."""

import re
from collections.abc import Awaitable, Callable

# Markdown-картинки, которые Docling вставляет в текст: ![Image](data:image/png;base64,...)
EMBEDDED_IMAGE_RE = re.compile(r"!\[Image\]\(data:image/[^;]+;base64,([^)]+)\)")
UNICODE_ESCAPE_RE = re.compile(r"/uni([0-9A-Fa-f]{4})")


def convert_unicode_escapes(text: str) -> str:
    """Заменяет последовательности вида /uni042F на соответствующие символы."""
    return UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def remove_embedded_images(text: str) -> str:
    return EMBEDDED_IMAGE_RE.sub("", text)


async def replace_images_with_ocr(text: str, recognize: Callable[[str], Awaitable[str | None]]) -> str:
    """
    Заменяет встроенные картинки результатом OCR.

    recognize получает PNG в base64 и возвращает текст либо None, если распознать не удалось
    (такая картинка просто удаляется).
    """
    parts: list[str] = []
    last_end = 0
    for match in EMBEDDED_IMAGE_RE.finditer(text):
        parts.append(text[last_end : match.start()])
        last_end = match.end()
        ocr_text = await recognize(match.group(1))
        if ocr_text:
            parts.append(f' Image OCR: "{ocr_text}"')
    parts.append(text[last_end:])
    return "".join(parts)
