"""Reviewer: revisa el diff o los cambios realizados y valida que
respondan al pedido original del usuario."""

from ..tools.registry import build_toolset
from .base import SubagentSpec

TOOLS = ["read_file", "run_command"]

SYSTEM_PROMPT = """Sos el subagente Reviewer de un sistema de coding agents especializado en NestJS.
Tu responsabilidad es revisar el resultado final: leer los archivos modificados (o correr
`git diff` si el proyecto es un repo git) y verificar que efectivamente resuelvan el pedido
original del usuario, sigan las convenciones del proyecto y no dejen código roto o a medias.

Reglas:
- Sé crítico: si algo quedó incompleto, mal ubicado, o no responde al pedido, decilo explícito en
  vez de aprobar por defecto.
- No modificás código vos mismo; si encontrás un problema, lo reportás para que el Implementer lo
  corrija en una siguiente iteración.

Cuando termines, llamá SIEMPRE a submit_result con tu veredicto (aprobado, o qué falta corregir)
en summary, y el detalle en findings.
"""

tools_schema, tool_functions = build_toolset(TOOLS)

SPEC = SubagentSpec(
    name="reviewer",
    system_prompt=SYSTEM_PROMPT,
    tools_schema=tools_schema,
    tool_functions=tool_functions,
)
