from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API Keys
    anthropic_api_key: str = ""
    google_api_key: str = ""

    # Google Docs
    google_service_account_json: str = ""  # サービスアカウントJSONファイルのパス
    gdoc_document_id: str = "146cyr_6rRT2YJ0MgOOYtE3Mk-2Y9JeMWgI0UWEHfGz4"  # 出力先ドキュメントID

    # D2D Account
    d2d_email: str = ""
    d2d_password: str = ""

    # Author info
    author_name: str = "賢者とユイの読書倶楽部"
    author_bio: str = "人気書籍の本質を、賢者とユイの対話形式でわかりやすくお届けします。"

    # Paths
    data_dir: Path = BASE_DIR / "data" / "books"
    output_epubs_dir: Path = BASE_DIR / "output" / "epubs"
    output_thumbnails_dir: Path = BASE_DIR / "output" / "thumbnails"
    output_reports_dir: Path = BASE_DIR / "output" / "reports"

    # Browser
    headless_browser: bool = True

    # Claude model
    claude_model: str = "claude-opus-4-6"

    # Imagen model
    imagen_model: str = "imagen-3.0-generate-002"

    # Research
    research_interval_days: int = 7
    max_books_per_run: int = 5

    # Book settings
    book_price_usd: float = 4.99
    book_language: str = "ja"


settings = Settings()
