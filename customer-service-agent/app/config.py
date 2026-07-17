"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    app_name: str = "智能客服 Agent"
    debug: bool = True
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM Provider
    llm_provider: str = "deepseek"

    # LLM (OpenAI-compatible)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_model_advanced: str = "deepseek-reasoner"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048

    # Conversation
    max_conversation_turns: int = 20
    summary_trigger_turns: int = 10
    session_ttl_seconds: int = 1800

    # Retrieval
    retrieval_top_k: int = 5
    retrieval_score_threshold: float = 0.6

    # Guardrails
    enable_input_filter: bool = True
    enable_output_filter: bool = True

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
