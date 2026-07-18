"""Memoria persistente por proyecto: sobrevive entre sesiones, más allá del
historial de una conversación puntual. Se guarda en
memory_store/<slug>/memory.json.

Guarda arquitectura detectada, archivos importantes, dependencias, comandos
útiles, convenciones, decisiones tomadas, bugs investigados y resúmenes de
sesiones previas, según pide la consigna del TP final.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import MEMORY_STORE_DIR as MEMORY_ROOT

DEFAULT_MEMORY: dict = {
    "architecture": "",
    "important_files": [],
    "dependencies": [],
    "useful_commands": [],
    "conventions": [],
    "decisions": [],
    "investigated_bugs": [],
    "session_summaries": [],
}


def project_slug(project_path: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", project_path.strip().lower()).strip("-")
    return slug or "default"


def _memory_path(project_path: str) -> Path:
    return MEMORY_ROOT / project_slug(project_path) / "memory.json"


def load_memory(project_path: str) -> dict:
    path = _memory_path(project_path)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_MEMORY))
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    merged = json.loads(json.dumps(DEFAULT_MEMORY))
    merged.update(data)
    return merged


def save_memory(project_path: str, memory: dict) -> None:
    path = _memory_path(project_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


def update_memory(project_path: str, **sections: Any) -> dict:
    """Actualiza secciones de la memoria. Listas se mergean sin duplicar;
    otros tipos (ej. architecture, un string) se reemplazan."""
    memory = load_memory(project_path)
    for key, value in sections.items():
        if key in memory and isinstance(memory[key], list) and isinstance(value, list):
            for item in value:
                if item not in memory[key]:
                    memory[key].append(item)
        else:
            memory[key] = value
    save_memory(project_path, memory)
    return memory


def append_session_summary(project_path: str, summary: str) -> dict:
    memory = load_memory(project_path)
    memory["session_summaries"].append(
        {"date": datetime.now(timezone.utc).isoformat(), "summary": summary}
    )
    save_memory(project_path, memory)
    return memory


def format_memory_for_prompt(memory: dict, max_summaries: int = 3) -> str:
    """Compacta la memoria en un resumen breve para inyectar en el system
    prompt del orquestador, en vez de volcar el JSON completo (evita mandar
    todo el historial/proyecto al modelo en cada turno)."""
    lines = []
    if memory.get("architecture"):
        lines.append(f"Arquitectura detectada: {memory['architecture']}")
    if memory.get("important_files"):
        lines.append("Archivos importantes: " + ", ".join(memory["important_files"][:10]))
    if memory.get("dependencies"):
        lines.append("Dependencias clave: " + ", ".join(memory["dependencies"][:10]))
    if memory.get("useful_commands"):
        lines.append("Comandos útiles: " + ", ".join(memory["useful_commands"][:10]))
    if memory.get("conventions"):
        lines.append("Convenciones: " + "; ".join(memory["conventions"][:10]))
    if memory.get("decisions"):
        lines.append("Decisiones previas: " + "; ".join(memory["decisions"][-5:]))
    if memory.get("investigated_bugs"):
        lines.append("Bugs investigados: " + "; ".join(memory["investigated_bugs"][-5:]))
    recent_sessions = memory.get("session_summaries", [])[-max_summaries:]
    if recent_sessions:
        lines.append("Resumen de sesiones previas:")
        for s in recent_sessions:
            lines.append(f"  - [{s['date'][:10]}] {s['summary']}")
    if not lines:
        return "(sin memoria previa para este proyecto)"
    return "\n".join(lines)
