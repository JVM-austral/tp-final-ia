"""Tool de shell: run_command. Portada de jtvc.py con timeout más alto para
soportar comandos de npm (install/build/test) que tardan más que 60s."""

import subprocess


def run_command(command: str, timeout: int = 180) -> str:
    """Ejecuta un comando de terminal y devuelve stdout + stderr."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        parts = []
        if result.stdout.strip():
            parts.append(f"STDOUT:\n{result.stdout.strip()}")
        if result.stderr.strip():
            parts.append(f"STDERR:\n{result.stderr.strip()}")
        parts.append(f"Return code: {result.returncode}")
        return "\n".join(parts) if parts else "(sin output)"
    except subprocess.TimeoutExpired:
        return f"Error: El comando tardó más de {timeout} segundos y fue cancelado."
    except Exception as e:
        return f"Error ejecutando el comando: {e}"
