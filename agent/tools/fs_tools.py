"""Tools de filesystem: read_file, write_file, list_files.

Portadas del TP de la cursada (jtvc.py), sin los prints de progreso: el
harness ya loguea cada tool call (nombre, args, preview del resultado), así
que estas funciones se mantienen puras (reciben args, devuelven un string).
"""

from pathlib import Path


def read_file(path: str) -> str:
    """Lee el contenido de un archivo dado su path."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found at {path}"
    except Exception as e:
        return f"Error reading file {path}: {e}"


def write_file(path: str, content: str) -> str:
    """Escribe contenido en un archivo, reemplazando su contenido actual."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Archivo escrito exitosamente: {path}"
    except Exception as e:
        return f"Error escribiendo '{path}': {e}"


def list_files(directory: str = ".") -> str:
    """Lista los archivos y carpetas en un directorio."""
    try:
        p = Path(directory)
        if not p.exists():
            return f"Error: El directorio '{directory}' no existe."
        items = sorted(p.iterdir())
        if not items:
            return "(directorio vacío)"
        lines = []
        for item in items:
            icon = "[dir]" if item.is_dir() else "[file]"
            lines.append(f"{icon} {item.name}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando '{directory}': {e}"
