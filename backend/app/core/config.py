"""
Application configuration using pydantic-settings.
"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./github_intelligence.db"
    REDIS_URL: str = "redis://localhost:6379"
    GITHUB_TOKEN: str = ""
    LLM_API_KEY: str = ""
    EMBEDDING_API_KEY: str = ""
    REPOSITORIES_DIR: Path = Path("repositories")
    MAX_REPOSITORY_SIZE_MB: int = 100
    MAX_FILE_SIZE_KB: int = 500
    ANALYSIS_TIMEOUT_SECONDS: int = 300
    GIT_TIMEOUT_SECONDS: int = 120
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
