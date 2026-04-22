from typing import List, Optional
import openai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import logging

logger = logging.getLogger(__name__)


class Embedding_Client:
    def __init__(
        self,
        api_key: str,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        deployment_name: str = "text-embedding-3-large",
    ) -> None:
        self._deployment_name = deployment_name
        if azure_endpoint:
            self._client = openai.AzureOpenAI(
                api_key=api_key,
                azure_endpoint=azure_endpoint,
                api_version=api_version or "2023-05-15",
            )
        else:
            self._client = openai.OpenAI(api_key=api_key)

    @retry(
        retry=retry_if_exception_type(openai.RateLimitError),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Envia todos os textos em uma única chamada batch à API OpenAI.
        Modelo: text-embedding-3-large (3072 dims).
        Retry com backoff exponencial apenas para HTTP 429 (max 5 tentativas).
        Outros erros HTTP são propagados imediatamente."""
        response = self._client.embeddings.create(
            model=self._deployment_name,
            input=texts,
        )
        return [item.embedding for item in response.data]
