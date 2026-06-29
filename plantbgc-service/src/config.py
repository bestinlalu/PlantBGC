import os

# pydantic_settings (v2) is available on Python 3.8+ (web).
# The bgc_worker runs Python 3.7 and uses pydantic v1 which ships BaseSettings built-in.
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        DATABASE_URL: str
        UPLOAD_DIR: str = "uploads"
        BASE_URL: str = "http://localhost:8000"

        model_config = SettingsConfigDict(extra="ignore")

except ImportError:
    # Pydantic v1 fallback — used by bgc_worker (Python 3.7)
    from pydantic import BaseSettings  # type: ignore[no-redef]

    class Settings(BaseSettings):  # type: ignore[no-redef]
        DATABASE_URL: str
        UPLOAD_DIR: str = "uploads"
        BASE_URL: str = "http://localhost:8000"

        class Config:
            extra = "ignore"

settings = Settings()

# Ensure upload directories exist on startup
os.makedirs(os.path.join(settings.UPLOAD_DIR, "raw"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "results"), exist_ok=True)
os.makedirs(os.path.join(settings.UPLOAD_DIR, "training"), exist_ok=True)
