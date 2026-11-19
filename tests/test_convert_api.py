import httpx
import respx

from tests.conftest import DOC_URL, OCR_URL, TEST_FILES, VLLM_URL, mock_docling_success


async def convert(client: httpx.AsyncClient, data: bytes, name: str, **form: str) -> httpx.Response:
    return await client.post("/convert", files={"file": (name, data)}, data=form)


async def test_docx_goes_through_docling(client: httpx.AsyncClient, mock_services: respx.MockRouter) -> None:
    mock_docling_success(mock_services, "# Заголовок /uni042F")
    data = (TEST_FILES / "test_document.docx").read_bytes()

    response = await convert(client, data, "doc.docx")

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "doc.docx"
    assert body["file_text"] == "# Заголовок Я"


async def test_text_pdf_goes_through_docling(
    client: httpx.AsyncClient, mock_services: respx.MockRouter, text_pdf: bytes
) -> None:
    mock_docling_success(mock_services, "pdf text")
    ocr = mock_services.post(f"{OCR_URL}/ocr").respond(text="scan")

    response = await convert(client, text_pdf, "doc.pdf")

    assert response.json()["file_text"] == "pdf text"
    assert not ocr.called


async def test_scanned_pdf_goes_to_ocr_server(
    client: httpx.AsyncClient, mock_services: respx.MockRouter, scanned_pdf: bytes
) -> None:
    mock_services.post(f"{OCR_URL}/ocr").respond(text="распознанный скан")

    response = await convert(client, scanned_pdf, "scan.pdf")

    assert response.json()["file_text"] == "распознанный скан"


async def test_force_ocr_for_text_pdf(
    client: httpx.AsyncClient, mock_services: respx.MockRouter, text_pdf: bytes
) -> None:
    mock_services.post(f"{OCR_URL}/ocr").respond(text="forced")

    response = await convert(client, text_pdf, "doc.pdf", force_ocr__only_pdf="true")

    assert response.json()["file_text"] == "forced"


async def test_image_goes_to_vllm(
    client: httpx.AsyncClient, mock_services: respx.MockRouter, png_image: bytes
) -> None:
    route = mock_services.post(f"{VLLM_URL}/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": " текст с картинки "}}]}
    )

    response = await convert(client, png_image, "image.png")

    assert response.json()["file_text"] == "текст с картинки"
    assert route.called


async def test_embedded_images_removed_by_default(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_docling_success(mock_services, "до ![Image](data:image/png;base64,AAAA) после")

    response = await convert(client, b"data", "doc.docx")

    assert response.json()["file_text"] == "до  после"


async def test_embedded_images_replaced_with_ocr(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_docling_success(mock_services, "до ![Image](data:image/png;base64,AAAA) после")
    mock_services.post(f"{VLLM_URL}/v1/chat/completions").respond(
        json={"choices": [{"message": {"content": "надпись"}}]}
    )

    response = await convert(client, b"data", "doc.docx", ocr_images_in_file="true")

    assert response.json()["file_text"] == 'до  Image OCR: "надпись" после'


async def test_failed_image_ocr_drops_image(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_docling_success(mock_services, "до ![Image](data:image/png;base64,AAAA) после")
    mock_services.post(f"{VLLM_URL}/v1/chat/completions").respond(status_code=500)

    response = await convert(client, b"data", "doc.docx", ocr_images_in_file="true")

    assert response.json()["file_text"] == "до  после"


async def test_unsupported_type_returns_400(client: httpx.AsyncClient) -> None:
    response = await convert(client, b"data", "archive.zip")
    assert response.status_code == 400


async def test_empty_file_returns_400(client: httpx.AsyncClient) -> None:
    response = await convert(client, b"", "doc.docx")
    assert response.status_code == 400


async def test_too_large_file_returns_413(client: httpx.AsyncClient) -> None:
    response = await convert(client, b"0" * (1024 * 1024 + 1), "doc.docx")
    assert response.status_code == 413


async def test_docling_failure_returns_502(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_services.post(f"{DOC_URL}/v1/convert/file/async").respond(json={"task_id": "t1"})
    mock_services.get(f"{DOC_URL}/v1/status/poll/t1").respond(json={"task_status": "failed", "error": "boom"})

    response = await convert(client, b"data", "doc.docx")

    assert response.status_code == 502
    assert "boom" in response.json()["detail"]


async def test_docling_unavailable_returns_502(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_services.post(f"{DOC_URL}/v1/convert/file/async").mock(side_effect=httpx.ConnectError("refused"))

    response = await convert(client, b"data", "doc.docx")

    assert response.status_code == 502
