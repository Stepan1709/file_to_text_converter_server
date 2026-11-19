import io
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from pypdf import PdfWriter

from app.clients.docling import DoclingClient
from app.clients.ocr_server import OcrServerClient
from app.clients.vllm import VllmClient
from app.core.config import Settings, get_settings
from app.main import create_app
from app.services.converter import ConverterService

DOC_URL = "http://docling.test"
VLLM_URL = "http://vllm.test"
OCR_URL = "http://ocr.test"
TEST_FILES = Path(__file__).resolve().parent.parent / "test_files"


@pytest.fixture
def text_pdf() -> bytes:
    return (TEST_FILES / "test_document.pdf").read_bytes()


@pytest.fixture
def scanned_pdf() -> bytes:
    """PDF без текстового слоя."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def png_image() -> bytes:
    return (TEST_FILES / "test_image.png").read_bytes()


@pytest.fixture
def mock_services() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
async def app(mock_services: respx.MockRouter) -> AsyncIterator[FastAPI]:
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: Settings(max_upload_size_mb=1)
    async with httpx.AsyncClient() as http:
        application.state.converter = ConverterService(
            docling=DoclingClient(http, DOC_URL, timeout=5, poll_interval=0),
            vllm=VllmClient(http, VLLM_URL, "paddle-model", api_key="", timeout=5),
            ocr_server=OcrServerClient(http, OCR_URL, timeout=5),
            pdf_min_text_length=100,
        )
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


def mock_docling_success(router: respx.MockRouter, markdown: str) -> None:
    router.post(f"{DOC_URL}/v1/convert/file/async").respond(json={"task_id": "t1"})
    router.get(f"{DOC_URL}/v1/status/poll/t1").respond(json={"task_status": "success"})
    router.get(f"{DOC_URL}/v1/result/t1").respond(json={"document": {"md_content": markdown}})
