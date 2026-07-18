"""Tool de búsqueda web: web_search vía Tavily. Portada de jtvc.py, leyendo
la API key de variables de entorno (.env) en vez de google.colab.userdata."""

import os
import requests


def web_search(query: str) -> str:
    """Busca información en la web usando la API de Tavily."""
    tavily_key = os.environ.get("TAVILY_API_KEY", "")

    if not tavily_key:
        return (
            "web_search no disponible: configurá TAVILY_API_KEY en el archivo .env. "
            "Podés obtener una clave gratis en tavily.com"
        )

    try:
        response = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": tavily_key, "query": query, "max_results": 5},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        results = data.get("results", [])
        if not results:
            return "No se encontraron resultados."
        lines = []
        for r in results:
            lines.append(
                f"**{r.get('title', 'Sin título')}**\n"
                f"URL: {r.get('url', '')}\n"
                f"{r.get('content', '')}"
            )
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"Error en web_search: {e}"
