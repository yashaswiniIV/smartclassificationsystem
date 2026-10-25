from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    database_url: str = "postgresql+asyncpg://civicpulse:civicpulse@localhost:5432/civicpulse"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-me-32-bytes-min!!"
    jwt_algorithm: str = "HS256"
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 7
    otp_ttl_min: int = 10

    # auth rate limits (fixed window per minute)
    auth_rate_per_min: int = 5

    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "civicpulse"
    s3_secret_key: str = "civicpulse123"
    s3_bucket: str = "civicpulse-media"

    cors_origins: list[str] = ["http://localhost:3000"]

    # AI / pipeline
    mock_ai: bool = True  # when true, LLM (Gemini) calls return deterministic fixtures
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    # 384-d, multilingual, paraphrase-tuned (great for dedup); available in fastembed/ONNX
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

    # Run the complaint pipeline inline (BackgroundTasks) vs enqueue to the arq worker.
    # Inline is the zero-extra-process dev/demo default; prod sets this false + runs the worker.
    pipeline_inline: bool = True

    # Dedup / categorization thresholds — CALIBRATED against ml/eval (see its README).
    # The paraphrase-MiniLM model scores true duplicates lower than e5 would, so these
    # are well below the naive 0.8+ guesses. Sweep: prec/recall at 0.60 = .83/.77,
    # at 0.65 = 1.0/.69.
    # show as a possible duplicate (human decides → favor recall)
    similar_check_min_sim: float = 0.60
    # auto-merge with no human → favor precision (1.0 on the eval set)
    auto_attach_min_sim: float = 0.65
    dedup_radius_m: int = 150
    category_confidence_min: float = 0.45  # below this, fall back to the LLM classifier


@lru_cache
def get_settings() -> Settings:
    return Settings()
