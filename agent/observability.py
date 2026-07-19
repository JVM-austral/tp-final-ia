"""Observabilidad con Langfuse: prompts, modelo, llamadas al LLM, tools
invocadas, documentos recuperados, búsquedas web, iteraciones, errores,
latencia, tokens y costo, según pide la consigna del TP final.

`langfuse.openai.OpenAI` (usado en agent/llm.py) ya traza cada llamada al
LLM automáticamente (prompt, modelo, tokens, latencia, costo). Acá se
agrega `observe_agent` para anidar el orquestador y cada subagente como
spans, y `log_tool_call` / `log_retrieval` para registrar eventos que no
son llamadas al LLM (tool calls, resultados de RAG) dentro de esa traza.

El SDK de Langfuse se degrada solo (no lanza excepciones, solo loguea una
advertencia) si no hay LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY configuradas,
así que estos helpers se pueden usar siempre sin chequear manualmente si
está habilitado.
"""

import os

from langfuse import Langfuse, get_client, observe

observe_agent = observe

if os.environ.get("LANGFUSE_PUBLIC_KEY"):
    # Inicializa el cliente explícitamente con un timeout acotado. Si no se
    # hace esto, get_client() lo crea solo con la config por default (sin
    # límite de tiempo propio, independiente del timeout del cliente de
    # OpenAI), y un problema de red al exportar spans puede colgar el
    # proceso sin que el timeout de agent/llm.py lo cubra.
    Langfuse(timeout=30)


def log_tool_call(subagent_name: str, tool_name: str, tool_args: dict, result: str) -> None:
    """Registra una tool call como evento anidado en la traza activa."""
    preview = result[:1500] + ("..." if len(result) > 1500 else "")
    get_client().create_event(
        name=f"tool:{subagent_name}:{tool_name}",
        input=tool_args,
        output=preview,
    )


def log_retrieval(query: str, results: list) -> None:
    """Registra los documentos recuperados por rag_search como evento, para
    que quede visible en la traza qué fuentes se consultaron."""
    get_client().create_event(
        name="rag:retrieval",
        input={"query": query},
        output=[{"source": r.get("source"), "heading": r.get("heading"), "score": r.get("score")} for r in results],
    )


def log_error(context: str, error: Exception) -> None:
    get_client().create_event(
        name=f"error:{context}",
        level="ERROR",
        status_message=str(error),
    )
