import httpx
import respx

from tests.conftest import DOC_URL, OCR_URL, VLLM_URL


async def test_live(client: httpx.AsyncClient) -> None:
    assert (await client.get("/live")).json() == {"status": "alive"}


async def test_health_all_services_up(client: httpx.AsyncClient, mock_services: respx.MockRouter) -> None:
    for url in (DOC_URL, VLLM_URL, OCR_URL):
        mock_services.get(f"{url}/health").respond(200)

    body = (await client.get("/health")).json()

    assert body == {"status": "healthy", "services": {"docling": True, "vllm": True, "ocr": True}}


async def test_health_degraded_when_service_down(
    client: httpx.AsyncClient, mock_services: respx.MockRouter
) -> None:
    mock_services.get(f"{DOC_URL}/health").respond(200)
    mock_services.get(f"{VLLM_URL}/health").mock(side_effect=httpx.ConnectError("refused"))
    mock_services.get(f"{OCR_URL}/health").respond(503)

    body = (await client.get("/health")).json()

    assert body["status"] == "degraded"
    assert body["services"] == {"docling": True, "vllm": False, "ocr": False}
