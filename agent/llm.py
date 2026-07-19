import os

from langfuse.openai import OpenAI

MODEL = os.environ.get("AGENT_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = "text-embedding-3-small"

_client: OpenAI | None = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        # Sin timeout explícito, el SDK espera hasta 10 minutos por llamada (y reintenta),
        # lo que ante un problema de red se siente como que el harness quedó colgado sin
        # ningún feedback. Con esto, una llamada lenta/rota falla en <=90s con un error
        # claro en vez de bloquear el proceso indefinidamente.
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"], timeout=90.0, max_retries=1)
    return _client
