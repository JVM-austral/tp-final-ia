"""Agente principal (orquestador).

Mantiene el TaskState compartido, decide si resuelve algo directamente con
sus tools base o delega en un subagente especializado (Explorer/Researcher/
Implementer/Tester/Reviewer), valida cada tool call contra los guardrails,
aplica plan mode y supervisión, detecta loops, resume historial largo y
persiste memoria del proyecto al terminar cada tarea.
"""

import json
from typing import Optional

from .context import LOOP_WARNING_MESSAGE, MAX_LOOP_WARNINGS, LoopDetector, compact_history
from .config import validate_tool_call
from .llm import MODEL, get_client
from .memory import append_session_summary, format_memory_for_prompt, load_memory, project_slug, update_memory
from .observability import log_tool_call, observe_agent
from .paths import MEMORY_STORE_DIR
from .state import TaskState
from .subagents import explorer, implementer, researcher, reviewer, tester
from .subagents.base import run_subagent
from .tools.registry import build_toolset

BASE_TOOL_NAMES = ["read_file", "run_command", "list_files", "web_search"]
DESTRUCTIVE_TOOLS = {"run_command"}

SUBAGENT_SPECS = {
    "explorer": explorer.SPEC,
    "researcher": researcher.SPEC,
    "implementer": implementer.SPEC,
    "tester": tester.SPEC,
    "reviewer": reviewer.SPEC,
}

DELEGATE_DESCRIPTIONS = {
    "explorer": (
        "Delegá en Explorer para entender el repositorio: estructura, convenciones, "
        "dependencias y archivos relevantes."
    ),
    "researcher": (
        "Delegá en Researcher para investigar en el RAG de NestJS (y la web como fallback) "
        "cómo implementar algo."
    ),
    "implementer": "Delegá en Implementer para escribir o modificar código siguiendo hallazgos previos.",
    "tester": "Delegá en Tester para correr build/tests/lint y validar los cambios.",
    "reviewer": "Delegá en Reviewer para revisar el resultado final contra el pedido original.",
}

MAX_ORCHESTRATOR_ITERATIONS = 15

SYSTEM_PROMPT_TEMPLATE = """Sos el agente principal de un sistema multiagente de coding \
especializado en NestJS. Coordinás el trabajo de subagentes especializados para resolver \
tareas de código sobre el proyecto en {workspace}.

Subagentes disponibles (delegate_to_<nombre>):
- explorer: entiende el repo (estructura, convenciones, archivos relevantes). Solo lectura.
- researcher: busca información en el RAG de NestJS y, si hace falta, en la web.
- implementer: escribe o modifica código. Es el único con permiso de escritura.
- tester: corre build/tests/lint y reporta resultados.
- reviewer: revisa el resultado final contra el pedido original.

Guías de comportamiento:
- IMPORTANTE: vos NO tenés la tool write_file. Nunca vas a poder escribir o modificar código \
directamente. CUALQUIER cambio de código (crear/editar archivos .ts, DTOs, módulos, etc.) tiene \
que pasar SIEMPRE por delegate_to_implementer. No existe otra forma de escribir código en este \
sistema.
- Para agregar funcionalidad nueva, seguí SIEMPRE este flujo completo, en orden: \
(1) delegate_to_explorer para entender el repo y sus convenciones (salvo que la memoria del \
proyecto ya te dé esa información con suficiente detalle), (2) delegate_to_researcher para \
buscar en el RAG de NestJS cómo implementar lo pedido, (3) delegate_to_implementer para escribir \
el código, (4) delegate_to_tester para correr build/tests, (5) delegate_to_reviewer para \
validar el resultado final. No te saltees pasos de este flujo para tareas de código nuevo.
- Tus propias tools (read_file, run_command, list_files, web_search) son solo para lecturas \
rápidas o preguntas puntuales del usuario que NO impliquen escribir código.
- CRÍTICO: cada vez que uses delegate_to_<subagente>, el campo instruction tiene que incluir el \
pedido ORIGINAL completo del usuario tal cual (campos, tipos, relaciones, nombres exactos), más \
los hallazgos relevantes de subagentes anteriores. Nunca lo resumas de forma que se pierdan \
detalles concretos (ej. nombres de campos como productId/quantity/status): copialos literales.
- Si un subagente devuelve status=blocked, NO insistas repitiendo lo mismo: explicale al \
usuario qué falta (el campo missing) y pedí la información o decisión que necesitás.
- Si detectás que estás repitiendo la misma acción sin avanzar, cambiá de estrategia o frená \
y pedí ayuda al usuario en vez de seguir iterando.
- Distinguí siempre en tu respuesta final si la información viene del repo, de la memoria del \
proyecto, del RAG, de la web, o de una inferencia propia.
- Respondé siempre en el idioma del usuario (español o inglés). Sé conciso pero completo.

Memoria persistente de este proyecto (de sesiones anteriores):
{memory_summary}
"""


def _delegate_tool_schema(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": f"delegate_to_{name}",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": f"Instrucción concreta y con contexto suficiente para el subagente {name}.",
                    }
                },
                "required": ["instruction"],
            },
        },
    }


class Orchestrator:
    def __init__(self, workspace: str, plan_mode: bool = False, supervision: bool = False):
        self.workspace = workspace
        self.plan_mode = plan_mode
        self.supervision = supervision
        self.client = get_client()
        self.base_tools_schema, self.base_tool_functions = build_toolset(BASE_TOOL_NAMES)
        self.delegate_tools_schema = [
            _delegate_tool_schema(name, desc) for name, desc in DELEGATE_DESCRIPTIONS.items()
        ]
        self.memory = load_memory(workspace)
        self.iteration_count = 0
        self.loop_detector = LoopDetector()
        self.task_state: Optional[TaskState] = None
        self.messages: list = []
        self.reset()

    def _build_system_prompt(self) -> str:
        return SYSTEM_PROMPT_TEMPLATE.format(
            workspace=self.workspace,
            memory_summary=format_memory_for_prompt(self.memory),
        )

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self._build_system_prompt()}]
        self.iteration_count = 0
        self.loop_detector.reset()

    def _print_subagent_tool_call(self, subagent_name: str, tool_name: str, tool_args: dict, result: str) -> None:
        preview = result[:250] + ("..." if len(result) > 250 else "")
        print(f"       [{subagent_name}:{tool_name}] args={json.dumps(tool_args, ensure_ascii=False)[:150]}")
        print(f"          -> {preview}")

    def ask_permission(self, tool_name: str, tool_args: dict) -> bool:
        print(f"\n[SUPERVISIÓN] El agente quiere ejecutar: {tool_name}")
        preview = json.dumps(tool_args, ensure_ascii=False, indent=2)
        if len(preview) > 400:
            preview = preview[:400] + "\n... (truncado)"
        print(f"   Argumentos:\n{preview}")
        answer = input("   ¿Permitir? [s/n] (Enter = sí): ").strip().lower()
        return answer in ("s", "si", "sí", "y", "yes", "")

    def _execute_base_tool(self, tool_name: str, tool_args: dict) -> str:
        validation = validate_tool_call(tool_name, tool_args)
        if not validation.allowed:
            return f"[Guardrail] Acción bloqueada: {validation.reason}"

        needs_confirmation = validation.requires_approval or (
            self.supervision and tool_name in DESTRUCTIVE_TOOLS
        )
        if needs_confirmation and not self.ask_permission(tool_name, tool_args):
            return "Acción cancelada por el usuario."

        func = self.base_tool_functions.get(tool_name)
        if func is None:
            return f"Error: tool '{tool_name}' no reconocida."
        try:
            result = func(**tool_args)
        except TypeError as e:
            return f"Error: argumentos inválidos para '{tool_name}': {e}"
        except Exception as e:
            return f"Error ejecutando '{tool_name}': {e}"
        if tool_name == "write_file" and self.task_state:
            self.task_state.record_file_modified(tool_args.get("path", ""))
        return result

    def generate_plan(self, user_message: str) -> str:
        planning_messages = self.messages + [
            {
                "role": "user",
                "content": (
                    "Antes de hacer cualquier cosa, describí un plan numerado y detallado de los "
                    "pasos que vas a seguir (incluyendo qué subagentes vas a usar) para resolver "
                    "la siguiente tarea. NO ejecutes ninguna herramienta todavía. Solo el plan.\n\n"
                    f"Tarea: {user_message}"
                ),
            }
        ]
        response = self.client.chat.completions.create(model=MODEL, messages=planning_messages)
        return response.choices[0].message.content or ""

    @observe_agent(name="orchestrator:turn", as_type="agent")
    def run_turn(self, user_message: str) -> str:
        self.task_state = TaskState(original_request=user_message)
        self.messages.append({"role": "user", "content": user_message})

        turn_iterations = 0
        final_text = ""

        while turn_iterations < MAX_ORCHESTRATOR_ITERATIONS:
            turn_iterations += 1
            self.iteration_count += 1
            self.messages = compact_history(self.client, MODEL, self.messages)

            print(f"\n[Iteración {turn_iterations} de este turno, total acumulado: {self.iteration_count}]")

            response = self.client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=self.base_tools_schema + self.delegate_tools_schema,
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
            self.messages.append(message_dict)

            if not message.tool_calls:
                final_text = message.content or ""
                break

            loop_stop = False
            for tc in message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                if tool_name.startswith("delegate_to_"):
                    subagent_name = tool_name[len("delegate_to_") :]
                    spec = SUBAGENT_SPECS.get(subagent_name)
                    if spec is None:
                        result_text = f"Error: subagente '{subagent_name}' no existe."
                    else:
                        instruction = tool_args.get("instruction", "")
                        print(f"\n  -> Delegando en {subagent_name}: {instruction[:120]}")
                        result = run_subagent(spec, self.task_state, instruction, on_tool_call=self._print_subagent_tool_call)
                        self.task_state.log_progress(
                            f"{subagent_name}: {result['status']} - {result['summary'][:200]}"
                        )
                        print(f"     status={result['status']} | {result['summary'][:200]}")
                        if result.get("sources"):
                            for src in result["sources"]:
                                print(f"     fuente [{src.get('kind')}]: {src.get('ref')}")
                        result_text = json.dumps(result, ensure_ascii=False)
                else:
                    print(f"\n  [{tool_name}] args: {json.dumps(tool_args, ensure_ascii=False)[:200]}")
                    result_text = self._execute_base_tool(tool_name, tool_args)
                    log_tool_call("orchestrator", tool_name, tool_args, result_text)
                    preview = result_text[:300] + ("..." if len(result_text) > 300 else "")
                    print(f"     -> {preview}")

                self.iteration_count += 1
                if self.loop_detector.record(tool_name, tool_args, result_text):
                    self.task_state.loop_warnings += 1
                    print(f"\n  [Sistema] Loop detectado: '{tool_name}' repitió los mismos argumentos y resultado 3+ veces.")
                    result_text += f"\n\n{LOOP_WARNING_MESSAGE}"
                    if self.task_state.loop_warnings >= MAX_LOOP_WARNINGS:
                        print("\n[Sistema] Loop detectado y no resuelto: freno el turno para pedir ayuda al usuario.")
                        final_text = (
                            "Detecté que estoy repitiendo la misma acción sin avanzar y no tengo evidencia "
                            "suficiente para seguir por mi cuenta. Necesito que me des más información o una "
                            "indicación distinta antes de continuar."
                        )
                        self.task_state.record_observation("Turno frenado por detección de loop.")
                        loop_stop = True

                self.messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_text})
                if loop_stop:
                    break

            if loop_stop:
                self.messages.append({"role": "assistant", "content": final_text})
                break

        if not final_text:
            final_text = "Alcancé el límite de iteraciones de este turno sin llegar a una respuesta final."

        self._finish_turn(final_text)
        return final_text

    def _finish_turn(self, final_text: str) -> None:
        self.task_state.log_progress(f"Respuesta final: {final_text[:200]}")

        slug = project_slug(self.workspace)
        self.task_state.save(MEMORY_STORE_DIR / slug / "last_task_state.json")

        updates: dict = {}
        explorer_result = self.task_state.subagent_results.get("explorer")
        if explorer_result and explorer_result.get("summary"):
            updates["architecture"] = explorer_result["summary"]
        if explorer_result and explorer_result.get("findings"):
            updates["important_files"] = list(explorer_result["findings"])
        if self.task_state.files_modified:
            updates["important_files"] = updates.get("important_files", []) + self.task_state.files_modified
        decision = f"Tarea: {self.task_state.original_request[:150]} -> {final_text[:150]}"
        updates["decisions"] = [decision]

        self.memory = update_memory(self.workspace, **updates)
        append_session_summary(
            self.workspace, f"{self.task_state.original_request[:200]} — {final_text[:200]}"
        )
