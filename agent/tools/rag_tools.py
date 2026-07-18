"""Tool de RAG: rag_search. Consulta el índice vectorial de documentación
oficial de NestJS y devuelve los chunks más relevantes junto con su fuente,
para que el agente pueda citarlas y diferenciar información obtenida del
RAG de la del repo, memoria, web o inferencia propia (como pide la
consigna). Si la relevancia es baja, sugiere usar web_search como fallback.
"""

MIN_RELEVANCE_SCORE = 0.25


def rag_search(query: str, k: int = 4) -> str:
    from ..llm import get_client
    from ..observability import log_retrieval
    from ..rag.store import query as query_index

    client = get_client()
    results = query_index(client, query, k=k)
    log_retrieval(query, results)

    if not results:
        return (
            "RAG: no se encontraron resultados (¿se corrió la ingesta? ver agent/rag/ingest.py). "
            "Usá web_search como fallback."
        )

    best_score = max(r["score"] for r in results)
    lines = [
        f"[fuente RAG: {r['source']} > {r['heading']}] (score={r['score']:.2f})\n{r['text']}"
        for r in results
    ]
    header = ""
    if best_score < MIN_RELEVANCE_SCORE:
        header = (
            "RAG: la relevancia de los resultados es baja, puede no haber evidencia suficiente "
            "en la documentación indexada para esta consulta. Considerá usar web_search como "
            "fallback antes de asumir algo.\n\n"
        )
    return header + "\n\n---\n\n".join(lines)
