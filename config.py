from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='/opt/tourism_platform/.env',
        env_file_encoding='utf-8',
    )

    redis_host: str = 'localhost'
    redis_port: int = 6379
    kb_dir: str = '/opt/tourism_platform/knowledge_bases'
    knowledge_index_path: str = '/opt/tourism_platform/generated/knowledge_index.json'
    knowledge_base_url: str = ''

    telegram_bot_token: str = ''
    llm_api_key: str = ''
    llm_model: str = 'openrouter/openrouter/free'
    llm_base_url: str = 'http://0.0.0.0:4000'


settings = Settings()
