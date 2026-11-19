"""Конфигурация сервиса. Все параметры задаются переменными окружения или файлом .env."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    doc_url: str = "http://localhost:9001"
    vllm_url: str = "http://localhost:8400"
    vllm_api_key: str = ""
    ocr_url: str = "http://localhost:9000"
    model_name: str = "PaddlePaddle/PaddleOCR-VL"

    docling_timeout: float = Field(3600.0, gt=0)
    docling_poll_interval: float = Field(10.0, ge=0)
    vllm_request_timeout: float = Field(300.0, gt=0)
    ocr_request_timeout: float = Field(3600.0, gt=0)
    pdf_min_text_length: int = Field(100, ge=0)
    max_upload_size_mb: int = Field(200, ge=1)

    host: str = "0.0.0.0"
    port: int = Field(8999, ge=1, le=65535)
    log_level: str = "INFO"

    @property
    def doc_base_url(self) -> str:
        return self.doc_url.rstrip("/")

    @property
    def vllm_base_url(self) -> str:
        return self.vllm_url.rstrip("/")

    @property
    def ocr_base_url(self) -> str:
        return self.ocr_url.rstrip("/")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
