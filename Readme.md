# File Converter Microservice

Микросервис для унифицированной конвертации различных типов файлов в текст с использованием Docling, OCR server и vLLM PaddleOCR-VL.

## 📋 Содержание

- [Обзор](#обзор)
- [Архитектура](#архитектура)
- [Поддерживаемые форматы](#поддерживаемые-форматы)
- [Требования](#требования)
- [Установка и настройка](#установка-и-настройка)
- [Запуск](#запуск)
- [API Endpoints](#api-endpoints)
- [Примеры использования](#примеры-использования)
- [Логирование](#логирование)
- [Устранение неполадок](#устранение-неполадок)

## 🚀 Обзор

Микросервис предоставляет единый API-интерфейс для конвертации документов в текст, скрывая сложность взаимодействия с тремя различными сервисами:

1. **Docling Serve** - для обработки офисных документов и PDF с текстом
2. **OCR Server** - для оптического распознавания символов в PDF-сканах
3. **vLLM PaddleOCR-VL** - для распознавания текста на изображениях

Сервис автоматически определяет тип файла и выбирает оптимальный способ обработки.

## 🏗️ Архитектура

```
┌─────────────────┐
│   Client        │
└────────┬────────┘
         │ HTTP POST /convert
         ▼
┌─────────────────────────────────────┐
│   File Converter Microservice       │
│   (FastAPI + Uvicorn)               │
│   Port: 8999                        │
└─────────┬───────────────────────────┘
          │
    ┌─────┴─────┬──────────┬──────────┐
    ▼           ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
│Docling │ │  OCR   │ │ vLLM   │ │Client  │
│ Serve  │ │Server  │ │Paddle- │ │Response│
│:9001   │ │:9000   │ │OCR-VL  │ │        │
└────────┘ └────────┘ │:8400   │ └────────┘
                      └────────┘
```

## 📁 Поддерживаемые форматы

| Тип файла | Расширения | Способ обработки |
|-----------|------------|------------------|
| Офисные документы | .docx, .pptx | Docling Serve |
| Веб-страницы | .html, .htm | Docling Serve |
| Текстовые форматы | .md, .csv | Docling Serve |
| Таблицы | .xlsx | Docling Serve |
| XML/JSON | .xml, .json | Docling Serve |
| Изображения | .png, .jpg, .jpeg, .gif, .bmp, .tiff | vLLM PaddleOCR-VL |
| PDF (текстовый) | .pdf | Docling Serve + опциональный OCR изображений |
| PDF (скан) | .pdf | OCR Server |

## 📋 Требования

- Docker (версия 20.10.0 или выше)
- Доступ к внешним сервисам:
  - Docling Serve
  - vLLM PaddleOCR-VL
  - [OCR Server](https://github.com/Stepan1709/PaddleOCR-VL_pdf_ocr_server)

## 🔧 Установка и настройка

### 1. Клонирование репозитория

```bash
git clone <repository-url>
cd file-converter-microservice
```

### 2. Настройка конфигурации

Отредактируйте файл `secrets.py` для указания URL ваших сервисов:

```python
# secrets.py
DOC_URL = "http://ip:port"  # URL Docling сервиса
VLLM_URL = "http://ip:port"  # URL vLLM сервиса
VLLM_API_KEY = "your_api_key_for_vllm"  # API ключ vLLM
OCR_URL = "http://ip:port"  # URL OCR сервера
MODEL_NAME = "PaddlePaddle/PaddleOCR-VL"  # Название модели
```

**Важно:** Все параметры конфигурации могут быть изменены. Если импорт из `secrets.py` не удастся, сервис автоматически использует `localhost` для URL и пустые значения для API ключей.

### 3. Проверка доступности сервисов

Перед запуском убедитесь, что все внешние сервисы доступны:

```bash
# Проверка Docling
curl http://ip:port/health

# Проверка vLLM
curl -H "Authorization: Bearer your_api_key_for_vllm" \
     http://ip:port/health

# Проверка OCR сервера
curl http://ip:port/health
```

## 🐳 Запуск

### Сборка Docker образа

```bash
docker build -t file-converter-server .
```

### Запуск контейнера

```bash
docker run -d \
  --name file-converter \
  -p 8999:8999 \
  --restart unless-stopped \
  file-converter-server
```

### Просмотр логов

```bash
# Показать последние 100 строк логов
docker logs --tail 100 file-converter

# Следить за логами в реальном времени
docker logs -f --tail 100 file-converter
```

### Остановка и удаление контейнера

```bash
# Остановка контейнера
docker stop file-converter

# Удаление контейнера
docker rm file-converter
```

## 📡 API Endpoints

### GET /health
Проверка здоровья сервиса и доступности внешних сервисов.

**Ответ:**
```json
{
  "status": "healthy",
  "services": {
    "docling": true,
    "vllm": true,
    "ocr": true
  }
}
```

### GET /docs
Получение документации API в текстовом формате.

**Ответ:**
```json
{
  "api_info": "API для конвертации файлов в текст\n\nЭндпоинты:\n- GET /health ..."
}
```

### POST /convert
Конвертация файла в текст.

**Параметры:**
- `file` (обязательный): файл для конвертации
- `force_ocr__only_pdf` (опциональный, bool, default: false): принудительное использование OCR сервера для PDF
- `ocr_images_in_file` (опциональный, bool, default: false): выполнять OCR для изображений внутри документа

**Успешный ответ (200):**
```json
{
  "filename": "document.pdf",
  "file_text": "Извлеченный текст документа...",
  "worktime": "00:00:05"
}
```

**Ошибки:**
- `400 Bad Request`: неподдерживаемый тип файла
- `500 Internal Server Error`: внутренняя ошибка сервера

## 📝 Примеры использования

### 1. Конвертация изображения

```bash
curl -X POST "http://localhost:8999/convert" \
  -F "file=@/path/to/image.png"
```

### 2. Конвертация PDF с текстом с OCR изображений внутри

```bash
curl -X POST "http://localhost:8999/convert" \
  -F "file=@/path/to/document.pdf" \
  -F "ocr_images_in_file=true"
```

### 3. Принудительное использование OCR сервера для PDF

```bash
curl -X POST "http://localhost:8999/convert" \
  -F "file=@/path/to/scanned.pdf" \
  -F "force_ocr__only_pdf=true"
```

### 4. Конвертация Word документа

```bash
curl -X POST "http://localhost:8999/convert" \
  -F "file=@/path/to/document.docx"
```

### 5. Использование Python requests

```python
import requests

url = "http://localhost:8999/convert"
files = {"file": open("document.pdf", "rb")}
data = {"force_ocr__only_pdf": False, "ocr_images_in_file": True}

response = requests.post(url, files=files, data=data)
result = response.json()

print(f"Filename: {result['filename']}")
print(f"Text length: {len(result['file_text'])}")
print(f"Processing time: {result['worktime']}")
```

## 📊 Логирование

Сервис логирует следующие события:

### Startup
```
🚀 Сервер запущен на http://0.0.0.0:8999
📡 Подключен к Docling: http://http://ip:port
📡 Подключен к OCR server: http://http://ip:port
📡 Подключен к vLLM: http://http://ip:port
🤖 Модель: PaddlePaddle/PaddleOCR-VL
Статус сервисов: Docling: True, vLLM: True, OCR: True
```

### Обработка файла
```
Получен файл: document.pdf, тип: pdf, размер: 123456 байт
Параметры: force_ocr_pdf=False, ocr_images=True
PDF document.pdf содержит текст, обработка через Docling
Ожидание завершения обработки файла document.pdf, Task ID: abc-123
Статус обработки document.pdf: processing, позиция: 1
Обработка файла document.pdf завершена за 00:00:15
```

### Ошибки
```
Ошибка обработки файла image.png: Connection refused to vLLM service
```

## 🔍 Устранение неполадок

### Проблемы с обработкой PDF

**Проблема:** PDF не распознается как скан
- Сервис использует PyPDF2 для извлечения текста
- Если извлечено <100 символов, PDF считается сканом
- Для принудительного использования OCR используйте параметр `force_ocr__only_pdf=true`

### Долгая обработка файлов

**Причина:** Docling использует асинхронную обработку с очередью
- Статус обработки проверяется каждые 10 секунд
- В логах отображается позиция в очереди каждые 30 секунд
- Для больших файлов время обработки может составлять несколько минут

## 🛠️ Разработка и тестирование

### Локальный запуск без Docker

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск сервера
python to_text_server.py
```

### Проверка работоспособности

```bash
# Health check
curl http://localhost:8999/health

# Тест с тестовым файлом
curl -X POST "http://localhost:8999/convert" \
  -F "file=@test.pdf"
```

## 📄 Лицензия

[Укажите вашу лицензию]

## 🤝 Поддержка

При возникновении проблем:
1. Проверьте логи контейнера: `docker logs --tail 100 file-converter`
2. Проверьте доступность внешних сервисов
3. Убедитесь в корректности настроек в `secrets.py`
4. Проверьте формат отправляемого файла

---

**Версия:** 1.0.0  
**Последнее обновление:** Апрель 2026
