FROM python:3.11-slim

WORKDIR /app

# Устанавливаем системные зависимости для работы с изображениями и PDF
RUN apt-get update && apt-get install -y \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY to_text_server.py .
COPY secrets.py .
COPY config.py .
COPY api_info.txt .

# Открываем порт
EXPOSE 8999

# Запускаем сервер
CMD ["uvicorn", "to_text_server:app", "--host", "0.0.0.0", "--port", "8999", "--log-level", "info"]