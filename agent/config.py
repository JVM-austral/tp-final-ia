import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ValidationResult:
    allowed: bool
    reason: str = ""
    requires_approval: bool = False


@dataclass
class GuardrailsConfig:
    workspace: Path
    read_deny: list = field(default_factory=list)
    write_deny: list = field(default_factory=list)
    command_deny: list = field(default_factory=list)
    command_require_approval: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "GuardrailsConfig":
        perms = data.get("permissions", {})
        cmds = data.get("commands", {})
        return cls(
            workspace=Path(data.get("workspace", ".")).resolve(),
            read_deny=perms.get("read", {}).get("deny", []),
            write_deny=perms.get("write", {}).get("deny", []),
            command_deny=cmds.get("deny", []),
            command_require_approval=cmds.get("require_approval", []),
        )


_config: Optional[GuardrailsConfig] = None


def load_config(config_path: str = "agent.config.yaml") -> GuardrailsConfig:
    global _config
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de configuración '{config_path}'")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    _config = GuardrailsConfig.from_dict(data)
    return _config


def get_config() -> GuardrailsConfig:
    if _config is None:
        raise RuntimeError("La configuración no fue cargada. Llamá a load_config() primero.")
    return _config


def _path_matches(path: str, pattern: str) -> bool:
    p = Path(path)
    normalized = str(p).replace("\\", "/")
    return fnmatch.fnmatch(p.name, pattern) or fnmatch.fnmatch(normalized, pattern)


def _check_sandbox(path: str) -> ValidationResult:
    cfg = get_config()
    try:
        candidate = Path(path)
        abs_path = candidate.resolve() if candidate.is_absolute() else (cfg.workspace / path).resolve()
        if not (abs_path == cfg.workspace or abs_path.is_relative_to(cfg.workspace)):
            return ValidationResult(
                False,
                f"Path '{path}' está fuera del workspace permitido ('{cfg.workspace}'). Resuelto: {abs_path}",
            )
    except (ValueError, OSError):
        return ValidationResult(False, f"No se pudo resolver el path '{path}' para validar el sandbox")
    return ValidationResult(True)


def _check_read(path: str) -> ValidationResult:
    if not path:
        return ValidationResult(True)
    sandbox = _check_sandbox(path)
    if not sandbox.allowed:
        return sandbox
    cfg = get_config()
    for pattern in cfg.read_deny:
        if _path_matches(path, pattern):
            return ValidationResult(False, f"Lectura de '{path}' bloqueada por política '{pattern}'")
    return ValidationResult(True)


def _check_write(path: str) -> ValidationResult:
    if not path:
        return ValidationResult(True)
    sandbox = _check_sandbox(path)
    if not sandbox.allowed:
        return sandbox
    cfg = get_config()
    for pattern in cfg.write_deny:
        if _path_matches(path, pattern):
            return ValidationResult(False, f"Escritura en '{path}' bloqueada por política '{pattern}'")
    return ValidationResult(True)


def _check_command(command: str) -> ValidationResult:
    if not command:
        return ValidationResult(True)
    cfg = get_config()
    command_lower = command.lower().strip()

    for banned in cfg.command_deny:
        if banned.lower() in command_lower:
            return ValidationResult(False, f"Comando prohibido detectado: '{banned}'")

    needs_approval = any(needle.lower() in command_lower for needle in cfg.command_require_approval)

    redirect_match = re.search(r">\s*(\S+)", command)
    if redirect_match:
        write_check = _check_write(redirect_match.group(1))
        if not write_check.allowed:
            return ValidationResult(False, f"Redirección a path bloqueado: {write_check.reason}")

    return ValidationResult(True, requires_approval=needs_approval)


def validate_tool_call(tool_name: str, tool_args: dict) -> ValidationResult:
    if _config is None:
        return ValidationResult(True)

    if tool_name == "read_file":
        return _check_read(tool_args.get("path", ""))
    if tool_name == "write_file":
        return _check_write(tool_args.get("path", ""))
    if tool_name == "list_files":
        return _check_sandbox(tool_args.get("directory", "."))
    if tool_name == "run_command":
        return _check_command(tool_args.get("command", ""))
    return ValidationResult(True)
