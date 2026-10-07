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

    # local | s3 | minio (v1 implements local only)
    storage: str = Field(default="local", alias="MODOOR_DOC_STORAGE")
    local_root: Path = Field(default=Path("./storage/doc"), alias="MODOOR_DOC_LOCAL_ROOT")
    s3_endpoint: str = Field(default="", alias="MODOOR_DOC_S3_ENDPOINT")
    s3_bucket: str = Field(default="", alias="MODOOR_DOC_S3_BUCKET")
    s3_access_key: str = Field(default="", alias="MODOOR_DOC_S3_ACCESS_KEY")
    s3_secret_key: str = Field(default="", alias="MODOOR_DOC_S3_SECRET_KEY")
    s3_region: str = Field(default="", alias="MODOOR_DOC_S3_REGION")
    s3_prefix: str = Field(default="doc/", alias="MODOOR_DOC_S3_PREFIX")
    ocr: bool = Field(default=True, alias="MODOOR_DOC_OCR")
    ocr_max_pages: int = Field(default=20, alias="MODOOR_DOC_OCR_MAX_PAGES")


@lru_cache
def get_doc_settings() -> DocSettings:
    return DocSettings()
