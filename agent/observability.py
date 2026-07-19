import os

from langfuse import Langfuse, get_client, observe

observe_agent = observe

if os.environ.get("LANGFUSE_PUBLIC_KEY"):
    Langfuse(timeout=30)


def log_tool_call(subagent_name: str, tool_name: str, tool_args: dict, result: str) -> None:
    preview = result[:1500] + ("..." if len(result) > 1500 else "")
    get_client().create_event(
        name=f"tool:{subagent_name}:{tool_name}",
        input=tool_args,
        output=preview,
    )


def log_retrieval(query: str, results: list) -> None:
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


def flush() -> None:
    if os.environ.get("LANGFUSE_PUBLIC_KEY"):
        get_client().flush()
