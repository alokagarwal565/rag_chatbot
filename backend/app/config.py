from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

from ingestion.config import ROOT_DIR

ENV_PATH = ROOT_DIR / ".env"


class Settings(BaseSettings):
    # LLM (Gemini). Keys are rotated on quota errors; models fall back per tier.
    gemini_api_key: str = ""
    gemini_api_key_2: Optional[str] = ""
    gemini_api_key_3: Optional[str] = ""

    llm_provider: str = "gemini"
    gemini_model_fast: str = "gemini-3.5-flash-lite"
    gemini_model_heavy: str = "gemini-3.6-flash"
    gemini_model_fallback_fast: str = "gemini-3.1-flash-lite"
    gemini_model_fallback_heavy: str = "gemini-3.5-flash"

    llm_timeout_seconds: float = 20.0
    llm_first_token_timeout_seconds: float = 8.0
    llm_max_output_tokens: int = 512
    rewrite_max_output_tokens: int = 64
    rewrite_timeout_seconds: float = 3.0
    llm_warmup: bool = True

    # Retrieval
    dense_top_k: int = 30
    lexical_top_k: int = 30
    rrf_k: int = 60
    rerank_candidates: int = 12
    context_top_k: int = 6
    context_token_limit: int = 3500
    retrieval_display_k: int = 10

    # Reranker (benchmarked on the target i3: 12 pairs x 256 tokens ~ 0.76 s)
    reranker_enabled: bool = True
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    reranker_max_length: int = 256

    # Abstention gate: sigmoid(rerank logit) of the best chunk must reach this.
    abstain_threshold: float = 0.002  # tuned on the eval set (evaluation/report.md, threshold sweep)
    # Used when the reranker is disabled: best RRF score must reach this.
    rrf_abstain_threshold: float = 0.016

    # Server
    port: int = 7860
    frontend_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def get_gemini_api_keys(self) -> List[str]:
        keys = [self.gemini_api_key, self.gemini_api_key_2, self.gemini_api_key_3]
        return [k.strip() for k in keys if k and k.strip()]


settings = Settings()
