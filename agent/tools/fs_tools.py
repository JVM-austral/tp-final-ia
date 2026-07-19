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
    """Escribe contenido en un archivo, reemplazando su contenido actual.

    Si el archivo ya existía, guarda su contenido previo en '<path>.bak'
    antes de sobreescribirlo (write_file reemplaza el archivo entero, no
    aplica un diff, así que un rewrite parcial del modelo puede perder
    contenido sin querer; el .bak permite recuperarlo). Si el contenido
    nuevo es mucho más corto que el anterior, lo avisa explícitamente para
    que el modelo pueda notar el problema y corregirlo.
    """
    try:
        target = Path(path)
        warning = ""
        if target.exists() and target.is_file():
            previous = target.read_text(encoding="utf-8", errors="replace")
            Path(str(target) + ".bak").write_text(previous, encoding="utf-8")
            if previous and len(content) < len(previous) * 0.5:
                warning = (
                    f" ADVERTENCIA: el contenido nuevo ({len(content)} caracteres) es mucho más "
                    f"corto que el anterior ({len(previous)} caracteres). Si no era intencional "
                    f"borrar esa parte del archivo, restaurá el contenido previo desde "
                    f"'{path}.bak' y reescribí de nuevo preservando todo lo que no querías cambiar."
                )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Archivo escrito exitosamente: {path}.{warning}"
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
