# file_to_text_converter_server

Микросервис, который превращает файлы любых популярных форматов в текст. Единый API скрывает три внешних сервиса
и сам выбирает, какой из них использовать для конкретного файла.

Часть RAG-пайплайна: его вызывает [s3_to_qdrant_synchronizer](https://github.com/Stepan1709/s3_to_qdrant_synchronizer).

## Архитектура

```
              POST /convert
Client ───────────────────────> file_to_text_converter_server (этот сервис, :8999)
                                        │
        ┌───────────────────────────────┼─────────────────────────────────┐
        ▼                               ▼                                 ▼
  Docling Serve               PaddleOCR-VL_pdf_ocr_server         vLLM + PaddleOCR-VL
  docx, pptx, html, md,       PDF-сканы (постраничный OCR)        изображения, картинки внутри
  csv, xlsx, xml, json,                                           документов (опционально)
  PDF с текстом
```

| Тип файла                                  | Расширения                                  | Обработка                                                  |
|--------------------------------------------|---------------------------------------------|------------------------------------------------------------|
| Офисные документы, веб, таблицы, разметка  | `.docx .pptx .html .htm .md .csv .xlsx .xml .json` | Docling Serve                                      |
| PDF с текстовым слоем                      | `.pdf`                                      | Docling Serve                                              |
| PDF-скан (текста < `PDF_MIN_TEXT_LENGTH`)  | `.pdf`                                      | [OCR-сервер](https://github.com/Stepan1709/PaddleOCR-VL_pdf_ocr_server) |
| Изображения                                | `.png .jpg .jpeg .gif .bmp .tiff`           | vLLM PaddleOCR-VL                                          |

Как определяется скан: из PDF извлекается текстовый слой (pypdf); если символов меньше `PDF_MIN_TEXT_LENGTH`
(по умолчанию 100) или PDF не читается, он считается сканом. Параметр `force_ocr__only_pdf=true` отправляет PDF
на OCR-сервер без проверки.

## Требования

Доступные по сети внешние сервисы:

- [Docling Serve](https://github.com/docling-project/docling-serve);
- vLLM с моделью `PaddlePaddle/PaddleOCR-VL`;
- [PaddleOCR-VL_pdf_ocr_server](https://github.com/Stepan1709/PaddleOCR-VL_pdf_ocr_server).

## Конфигурация

Все параметры задаются переменными окружения (шаблон — `.env.example`). Файл `.env` с ключами в git не попадает.

| Переменная              | По умолчанию                | Описание                                                  |
|-------------------------|-----------------------------|-----------------------------------------------------------|
| `DOC_URL`               | `http://localhost:9001`     | URL Docling Serve                                         |
| `VLLM_URL`              | `http://localhost:8400`     | URL vLLM                                                  |
| `VLLM_API_KEY`          | пусто                       | API-ключ vLLM                                             |
| `MODEL_NAME`            | `PaddlePaddle/PaddleOCR-VL` | Имя модели в vLLM                                         |
| `OCR_URL`               | `http://localhost:9000`     | URL OCR-сервера для PDF                                   |
| `DOCLING_TIMEOUT`       | `3600`                      | Максимальное время ожидания задачи в Docling, сек         |
| `DOCLING_POLL_INTERVAL` | `10`                        | Интервал опроса статуса задачи в Docling, сек             |
| `VLLM_REQUEST_TIMEOUT`  | `300`                       | Таймаут запроса к vLLM, сек                               |
| `OCR_REQUEST_TIMEOUT`   | `3600`                      | Таймаут запроса к OCR-серверу, сек                        |
| `PDF_MIN_TEXT_LENGTH`   | `100`                       | Порог текста, ниже которого PDF считается сканом          |
| `MAX_UPLOAD_SIZE_MB`    | `200`                       | Максимальный размер загружаемого файла, МБ                |
| `HOST` / `PORT`         | `0.0.0.0` / `8999`          | Адрес и порт сервиса (в Docker-образе проброшен `8999`)   |
| `LOG_LEVEL`             | `INFO`                      | Уровень логирования                                       |

## Запуск

### Docker Compose

```bash
git clone https://github.com/Stepan1709/file_to_text_converter_server
cd file_to_text_converter_server
cp .env.example .env      # укажите адреса сервисов и ключ vLLM
docker compose up -d --build
docker compose logs -f
```

### Docker

```bash
docker build -t file-converter-server .
docker run -d --name file-converter -p 8999:8999 --env-file .env --restart unless-stopped file-converter-server
docker logs -f --tail 100 file-converter
```

### Локально

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DOC_URL=http://<host>:9001 VLLM_URL=http://<host>:8400 OCR_URL=http://<host>:9000
python -m app
```

## API

| Метод  | Путь       | Описание                                                                        |
|--------|------------|---------------------------------------------------------------------------------|
| `POST` | `/convert` | Конвертация файла в текст                                                       |
| `GET`  | `/live`    | Liveness-проба (используется в `HEALTHCHECK`, внешние сервисы не проверяет)     |
| `GET`  | `/health`  | Доступность Docling, vLLM и OCR-сервера (`healthy` / `degraded`)                |
| `GET`  | `/docs`    | Swagger UI                                                                      |

### `POST /convert`

Multipart-форма:

- `file` (обязательный) — файл;
- `force_ocr__only_pdf` (bool, по умолчанию `false`) — для PDF: сразу отправить на OCR-сервер;
- `ocr_images_in_file` (bool, по умолчанию `false`) — для файлов, обрабатываемых Docling: распознавать встроенные
  изображения через vLLM (иначе они удаляются из текста). Для изображений параметры игнорируются.

Ответ `200`:

```json
{"filename": "document.pdf", "file_text": "Извлечённый текст...", "worktime": "0:00:05"}
```

Ошибки: `400` — неподдерживаемый тип или пустой файл, `413` — файл больше `MAX_UPLOAD_SIZE_MB`, `502` — внешний сервис
(Docling, vLLM, OCR-сервер) недоступен или вернул ошибку, `504` — внешний сервис не ответил вовремя, `500` — прочие ошибки.

### Примеры

```bash
curl -X POST http://localhost:8999/convert -F "file=@image.png"
curl -X POST http://localhost:8999/convert -F "file=@document.pdf" -F "ocr_images_in_file=true"
curl -X POST http://localhost:8999/convert -F "file=@scan.pdf" -F "force_ocr__only_pdf=true"
```

```python
import requests

with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8999/convert",
        files={"file": f},
        data={"ocr_images_in_file": True},
    )
result = response.json()
print(result["filename"], len(result["file_text"]), result["worktime"])
```

В каталоге `test_files/` лежат примеры файлов для проверки.

## Устранение неполадок

- **PDF-скан ушёл в Docling (или наоборот)** — порог определения скана настраивается через `PDF_MIN_TEXT_LENGTH`,
  принудительный OCR — через `force_ocr__only_pdf=true`.
- **Долгая обработка** — Docling работает через очередь; статус опрашивается каждые `DOCLING_POLL_INTERVAL` секунд,
  а по истечении `DOCLING_TIMEOUT` запрос завершается ошибкой. OCR больших сканов тоже занимает минуты
  (см. `OCR_REQUEST_TIMEOUT`).
- **`/health` возвращает `degraded`** — проверьте, какой из сервисов в `services` равен `false`, и его адрес в `.env`.

## Структура проекта

```
app/
├── main.py            # сборка приложения и lifespan (создание HTTP-клиента и сервисов)
├── __main__.py        # запуск: python -m app
├── core/              # конфигурация, логирование, исключения
├── api/
│   ├── deps.py        # зависимости FastAPI
│   └── routers/       # HTTP-эндпоинты (convert, health)
├── schemas/           # pydantic-схемы ответов
├── services/          # выбор способа обработки файла, очистка текста, работа с PDF и изображениями
└── clients/           # клиенты Docling, vLLM и OCR-сервера
tests/                 # pytest
```

## Разработка

```bash
pip install -r requirements-dev.txt
pre-commit install          # ruff и mypy перед каждым коммитом
ruff check . && ruff format --check . && mypy app
pytest
```

Те же проверки запускаются в GitHub Actions (`.github/workflows/ci.yml`).
