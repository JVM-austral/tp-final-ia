"""Runner genérico de subagentes.

Cada subagente (Explorer, Researcher, Implementer, Tester, Reviewer) tiene
su propio system prompt y un set acotado de tools. `run_subagent` lo corre
como un loop de tool-calling independiente del orquestador principal
(mismo patrón que el harness de la cursada, pero con su propio historial
de mensajes) y, al terminar, guarda un resultado estructurado en el
TaskState compartido en vez de volcarle al agente principal todo el
detalle de cada paso intermedio.
"""

import json
from dataclasses import dataclass

from ..config import validate_tool_call
from ..context import LOOP_WARNING_MESSAGE, MAX_LOOP_WARNINGS, LoopDetector
from ..llm import MODEL, get_client
from ..observability import log_tool_call, observe_agent
from ..state import TaskState

MAX_SUBAGENT_ITERATIONS = 25


@dataclass
class SubagentSpec:
    name: str
    system_prompt: str
    tools_schema: list
    tool_functions: dict


def _submit_result_tool() -> dict:
    return {
        "type": "function",
        "function": {
            "name": "submit_result",
            "description": (
                "Entregá el resultado final de tu trabajo. Llamalo SIEMPRE al terminar, "
                "en vez de responder solo con texto."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["done", "blocked"]},
                    "summary": {"type": "string", "description": "Resumen breve de lo que hiciste o encontraste."},
                    "findings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Hallazgos concretos: archivos, decisiones, resultados de comandos.",
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": ["repo", "memory", "rag", "web", "inference"],
                                },
                                "ref": {"type": "string"},
                            },
                            "required": ["kind", "ref"],
                        },
                        "description": "Fuentes consultadas para llegar al resultado.",
                    },
                    "missing": {
                        "type": "string",
                        "description": "Si status=blocked: qué información falta o qué se necesita para seguir.",
                    },
                },
                "required": ["status", "summary"],
            },
        },
    }


def run_subagent(spec: SubagentSpec, task_state: TaskState, instruction: str, on_tool_call=None) -> dict:
    """Corre el loop de tool-calling de un subagente y devuelve su
    resultado estructurado (también queda registrado en task_state)."""
    return observe_agent(name=f"subagent:{spec.name}", as_type="agent")(_run_subagent_impl)(
        spec, task_state, instruction, on_tool_call
    )


def _run_subagent_impl(spec: SubagentSpec, task_state: TaskState, instruction: str, on_tool_call=None) -> dict:
    client = get_client()
    tools = spec.tools_schema + [_submit_result_tool()]

    messages = [
        {"role": "system", "content": spec.system_prompt},
        {"role": "user", "content": instruction},
    ]

    loop_detector = LoopDetector()
    final_result = None

    for iteration in range(MAX_SUBAGENT_ITERATIONS):
        remaining = MAX_SUBAGENT_ITERATIONS - iteration
        if remaining == 5:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Te quedan pocas iteraciones disponibles. Dejá de explorar/investigar y "
                        "llamá a submit_result AHORA con lo que tengas hasta el momento (usá "
                        "status=blocked y explicá en missing qué te faltó si no llegaste a "
                        "terminar del todo)."
                    ),
                }
            )
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        message = response.choices[0].message

        message_dict = {"role": "assistant"}
        if message.content:
            message_dict["content"] = message.content
        if message.tool_calls:
            message_dict["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ]
        messages.append(message_dict)

        if not message.tool_calls:
            final_result = {
                "status": "done",
                "summary": message.content or "(sin resumen)",
                "findings": [],
                "sources": [],
                "missing": "",
            }
            break

        stop = False
        for tc in message.tool_calls:
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            if tool_name == "submit_result":
                final_result = {
                    "status": tool_args.get("status", "done"),
                    "summary": tool_args.get("summary", ""),
                    "findings": tool_args.get("findings", []),
                    "sources": tool_args.get("sources", []),
                    "missing": tool_args.get("missing", ""),
                }
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "Resultado recibido."})
                stop = True
                continue

            validation = validate_tool_call(tool_name, tool_args)
            if not validation.allowed:
                result = f"[Guardrail] Acción bloqueada: {validation.reason}"
            else:
                func = spec.tool_functions.get(tool_name)
                if func is None:
                    result = f"Error: tool '{tool_name}' no disponible para el subagente {spec.name}."
                else:
                    try:
                        result = func(**tool_args)
                    except TypeError as e:
                        result = f"Error: argumentos inválidos para '{tool_name}': {e}"
                    except Exception as e:
                        result = f"Error ejecutando '{tool_name}': {e}"

            log_tool_call(spec.name, tool_name, tool_args, result)
            if on_tool_call:
                on_tool_call(spec.name, tool_name, tool_args, result)

            task_state.iteration_count += 1
            if loop_detector.record(tool_name, tool_args, result):
                task_state.loop_warnings += 1
                result += f"\n\n{LOOP_WARNING_MESSAGE}"
                if task_state.loop_warnings >= MAX_LOOP_WARNINGS:
                    final_result = {
                        "status": "blocked",
                        "summary": f"El subagente {spec.name} se detuvo por repetición sin avance.",
                        "findings": [],
                        "sources": [],
                        "missing": (
                            "Se repitió la misma acción varias veces sin progreso; "
                            "hace falta intervención del usuario."
                        ),
                    }
                    stop = True

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        if stop:
            break

    if final_result is None:
        final_result = {
            "status": "blocked",
            "summary": f"El subagente {spec.name} no terminó en {MAX_SUBAGENT_ITERATIONS} iteraciones.",
            "findings": [],
            "sources": [],
            "missing": "Alcanzó el límite de iteraciones sin resultado final.",
        }

    task_state.record_subagent_result(spec.name, final_result)
    return final_result
