"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Groq API Key
    groq_api_key: Optional[str] = Field(default=None, alias="GROQ_API_KEY")

    # Default LLM provider
    default_llm: str = Field(default="groq", alias="DEFAULT_LLM")

    # Content extraction settings
    max_content_length: int = Field(default=6000, alias="MAX_CONTENT_LENGTH")
    request_timeout: int = Field(default=15, alias="REQUEST_TIMEOUT")

    # Server settings
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=4000, alias="PORT")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
        "populate_by_name": True,
    }


settings = Settings()
