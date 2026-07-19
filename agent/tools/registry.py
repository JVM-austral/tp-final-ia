"""Registro central de tools: función + schema JSON (formato OpenAI
tool-calling) para cada tool disponible. Cada subagente arma su propio
subset con build_toolset() según qué permisos necesita — no todos tienen
acceso a las mismas tools, como pide la consigna del TP final.
"""

from .fs_tools import list_files, read_file, write_file
from .rag_tools import rag_search
from .shell_tools import run_command
from .web_tools import web_search

ALL_TOOL_FUNCTIONS = {
    "read_file": read_file,
    "write_file": write_file,
    "run_command": run_command,
    "list_files": list_files,
    "web_search": web_search,
    "rag_search": rag_search,
}

# Tools que modifican el sistema: en modo supervisión piden confirmación antes
# de ejecutarse, sea quien sea que las invoque (agente principal o subagente).
DESTRUCTIVE_TOOLS = {"write_file", "run_command"}

ALL_TOOLS_SCHEMA = {
    "read_file": {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee el contenido de un archivo dado su path.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path del archivo a leer."}},
                "required": ["path"],
            },
        },
    },
    "write_file": {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Escribe contenido en un archivo, reemplazando su contenido actual. "
                "Crea directorios intermedios si no existen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path donde escribir el archivo."},
                    "content": {"type": "string", "description": "Contenido completo a escribir."},
                },
                "required": ["path", "content"],
            },
        },
    },
    "run_command": {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Ejecuta un comando de terminal y devuelve stdout y stderr.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string", "description": "El comando a ejecutar."}},
                "required": ["command"],
            },
        },
    },
    "list_files": {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lista los archivos y carpetas en un directorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directorio a listar.", "default": "."}
                },
                "required": [],
            },
        },
    },
    "web_search": {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Busca información en la web (Tavily) y devuelve los resultados más relevantes. "
                "Usar como fallback cuando el RAG no tiene evidencia suficiente."
            ),
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "La búsqueda a realizar."}},
                "required": ["query"],
            },
        },
    },
    "rag_search": {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Busca en la documentación oficial de NestJS indexada (RAG) y devuelve los "
                "fragmentos más relevantes junto con su fuente. Consultar esto ANTES de web_search."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La consulta a buscar en la documentación."},
                    "k": {"type": "integer", "description": "Cantidad de resultados a devolver.", "default": 4},
                },
                "required": ["query"],
            },
        },
    },
}


def build_toolset(names: list):
    """Arma (tools_schema, tool_functions) para un subset de nombres de tools."""
    schema = [ALL_TOOLS_SCHEMA[n] for n in names]
    functions = {n: ALL_TOOL_FUNCTIONS[n] for n in names}
    return schema, functions


def filter_known_args(tool_name: str, tool_args: dict) -> dict:
    """Descarta argumentos que el modelo haya alucinado y no existan en el
    schema de la tool (ej. pasar 'k' a web_search, que solo lo tiene
    rag_search). El schema de tool-calling no impide que el modelo invente
    parámetros extra, así que sin este filtro esas llamadas fallan con
    TypeError en vez de ejecutarse con los argumentos válidos que sí tiene."""
    schema = ALL_TOOLS_SCHEMA.get(tool_name)
    if schema is None:
        return tool_args
    known = set(schema["function"]["parameters"].get("properties", {}).keys())
    return {k: v for k, v in tool_args.items() if k in known}
