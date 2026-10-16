"""Doc module settings (deployment env — not kernel Settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DocSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # local | aliyun-oss | s3 | minio (s3/minio are not wired).
    # local root is always written; with aliyun-oss it is a cache and may be deleted.
    storage: str = Field(default="local", alias="MODOOR_STORAGE_TYPE")
    local_root: Path = Field(default=Path("./storage/doc"), alias="MODOOR_STORAGE_ROOT")
    oss_endpoint: str = Field(default="", alias="MODOOR_ALIYUN_OSS_ENDPOINT")
    oss_bucket: str = Field(default="", alias="MODOOR_ALIYUN_OSS_BUCKET")
    oss_ak_id: str = Field(default="", alias="MODOOR_ALIYUN_OSS_AK_ID")
    oss_ak_secret: str = Field(default="", alias="MODOOR_ALIYUN_OSS_AK_SECRET")
    oss_prefix: str = Field(default="doc/", alias="MODOOR_ALIYUN_OSS_PREFIX")
    s3_endpoint: str = Field(default="", alias="MODOOR_DOC_S3_ENDPOINT")
    s3_bucket: str = Field(default="", alias="MODOOR_DOC_S3_BUCKET")
    s3_access_key: str = Field(default="", alias="MODOOR_DOC_S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="MODOOR_DOC_S3_SECRET_KEY")
    s3_region: str = Field(default="", alias="MODOOR_DOC_S3_REGION")
    s3_prefix: str = Field(default="doc/", alias="MODOOR_DOC_S3_PREFIX")
    ocr: bool = Field(default=True, alias="MODOOR_DOC_OCR")
    # tesseract | external. External posts image bytes to MODOOR_OCR_URL.
    ocr_backend: str = Field(default="tesseract", alias="MODOOR_OCR_BACKEND")
    ocr_url: str = Field(default="", alias="MODOOR_OCR_URL")
    ocr_lang: str = Field(default="chi_sim+eng", alias="MODOOR_OCR_LANG")
    ocr_max_pages: int = Field(default=20, alias="MODOOR_DOC_OCR_MAX_PAGES")


@lru_cache
def get_doc_settings() -> DocSettings:
    return DocSettings()
