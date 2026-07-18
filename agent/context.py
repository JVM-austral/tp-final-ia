"""Manejo de contexto: resume historial largo y detecta loops (repetición
de acciones sin avance), para forzar replanificación o frenar y pedir ayuda
en vez de seguir iterando sin sentido, tal como pide la consigna del TP
final.
"""

import hashlib
import json

MAX_RAW_MESSAGES = 20
KEEP_RECENT_MESSAGES = 10
LOOP_REPEAT_THRESHOLD = 3
MAX_LOOP_WARNINGS = 2

LOOP_WARNING_MESSAGE = (
    "[Sistema] Detecté que estás repitiendo la misma acción (misma tool, mismos "
    "argumentos, mismo resultado) sin avanzar. Cambiá de estrategia: probá otro "
    "enfoque, replanificá los pasos, o si no tenés evidencia suficiente para "
    "continuar, explicá qué información falta y pedí ayuda al usuario en vez de "
    "reintentar lo mismo."
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class LoopDetector:
    """Trackea (tool, args_hash, result_hash) de las últimas tool calls para
    detectar repetición sin avance."""

    def __init__(self, window: int = 6):
        self.window = window
        self.history: list = []

    def record(self, tool_name: str, tool_args: dict, result: str) -> bool:
        """Registra una tool call y devuelve True si detecta un loop (misma
        tool+args+resultado repetido >= LOOP_REPEAT_THRESHOLD veces entre las
        últimas `window` llamadas)."""
        args_hash = _hash(json.dumps(tool_args, sort_keys=True, ensure_ascii=False))
        result_hash = _hash(result)
        entry = (tool_name, args_hash, result_hash)
        self.history.append(entry)
        self.history = self.history[-self.window :]
        return self.history.count(entry) >= LOOP_REPEAT_THRESHOLD

    def reset(self) -> None:
        self.history = []


def summarize_messages(client, model: str, messages: list) -> str:
    """Le pide al LLM un resumen compacto de una tanda de mensajes viejos,
    preservando decisiones y hallazgos relevantes."""
    convo_text = "\n".join(
        f"[{m.get('role')}] {m.get('content') or m.get('tool_calls') or ''}" for m in messages
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "Resumí de forma compacta el siguiente fragmento de una conversación "
                    "entre un agente de coding y un usuario. Conservá decisiones tomadas, "
                    "hallazgos importantes, archivos mencionados y resultados de comandos "
                    "relevantes. No inventes información nueva."
                ),
            },
            {"role": "user", "content": convo_text},
        ],
    )
    return response.choices[0].message.content or ""


def _find_safe_cut(rest: list, target_keep: int) -> int:
    """Busca un índice cercano a `target_keep` (desde el final) que sea
    seguro para cortar el historial: justo antes de un mensaje 'user', para
    no separar un tool_call de su respuesta."""
    ideal = max(len(rest) - target_keep, 0)
    for i in range(ideal, len(rest)):
        if rest[i].get("role") == "user":
            return i
    return len(rest)


def compact_history(client, model: str, messages: list) -> list:
    """Si el historial (sin contar el system prompt) supera MAX_RAW_MESSAGES,
    colapsa los mensajes más viejos en un resumen y deja los últimos
    KEEP_RECENT_MESSAGES intactos. Evita mandar todo el historial completo al
    modelo en cada turno."""
    if not messages:
        return messages
    system_msgs = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= MAX_RAW_MESSAGES:
        return messages

    cut = _find_safe_cut(rest, KEEP_RECENT_MESSAGES)
    if cut <= 0 or cut >= len(rest):
        return messages

    to_summarize, recent = rest[:cut], rest[cut:]
    summary_text = summarize_messages(client, model, to_summarize)
    summary_msg = {
        "role": "system",
        "content": f"[Resumen de {len(to_summarize)} mensajes previos]\n{summary_text}",
    }
    return system_msgs + [summary_msg] + recent
