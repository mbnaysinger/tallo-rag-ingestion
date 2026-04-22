from dataclasses import dataclass
import os
from typing import Optional

from dotenv import load_dotenv

REQUIRED_VARS = ["OPENAI_API_KEY", "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    sql_dialect: str  # "sybase" | "oracle" | "sqlserver" | "unknown"
    # Azure OpenAI (opcionais — se ausentes, usa OpenAI padrão)
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_version: Optional[str] = None
    azure_openai_deployment: str = "text-embedding-3-large"


def load_settings() -> Settings:
    """Carrega variáveis de ambiente via python-dotenv.
    Levanta EnvironmentError listando variáveis ausentes se obrigatórias faltarem."""
    load_dotenv()

    missing = [var for var in REQUIRED_VARS if not os.getenv(var)]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

    return Settings(
        openai_api_key=os.environ["OPENAI_API_KEY"],
        db_host=os.environ["DB_HOST"],
        db_port=int(os.environ["DB_PORT"]),
        db_name=os.environ["DB_NAME"],
        db_user=os.environ["DB_USER"],
        db_password=os.environ["DB_PASSWORD"],
        sql_dialect=os.getenv("SQL_DIALECT", "unknown"),
        azure_openai_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_openai_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT", "text-embedding-3-large"),
    )
