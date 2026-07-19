import os
import sys

if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


sys.stdout.reconfigure(line_buffering=True)

from dotenv import load_dotenv

load_dotenv()

from agent.config import load_config
from agent.observability import flush as flush_observability
from agent.orchestrator import Orchestrator

CONFIG_PATH = "agent.config.yaml"


def print_help():
    print(
        """
============================================================
              Comandos del Coding Agent
============================================================
  /plan on|off        Activa/desactiva el plan mode
  /supervision on|off Activa/desactiva la supervision
  /status             Muestra el estado de los modos
  /clear              Limpia el historial (conserva memoria persistente)
  /help               Muestra esta ayuda
  /exit               Sale del chat
============================================================
"""
    )


def print_status(orch: Orchestrator) -> None:
    plan = "ON" if orch.plan_mode else "OFF"
    sup = "ON" if orch.supervision else "OFF"
    print(f"\nPlan mode: {plan}   Supervision: {sup}   Iteraciones totales: {orch.iteration_count}")


def run_chat() -> None:
    cfg = load_config(CONFIG_PATH)
    os.chdir(cfg.workspace)

    print("=" * 60)
    print("Coding Agent Avanzado - TP Final (NestJS)")
    print(f"Workspace: {cfg.workspace}")
    print("=" * 60)
    print("Escribi tu tarea o /help para ver los comandos.\n")

    orch = Orchestrator(workspace=str(cfg.workspace), plan_mode=False, supervision=False)

    from agent.memory import format_memory_summary_for_console

    print("Memoria persistente: " + format_memory_summary_for_console(orch.memory))

    print_status(orch)

    while True:
        try:
            user_input = input("\nVos: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nHasta luego!")
            flush_observability()
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            parts = user_input.split()
            cmd = parts[0].lower()

            if cmd in ("/exit", "/quit", "/salir"):
                print("Hasta luego!")
                flush_observability()
                break
            elif cmd == "/help":
                print_help()
            elif cmd == "/status":
                print_status(orch)
            elif cmd == "/clear":
                orch.reset()
                print("Historial de conversacion reiniciado (la memoria persistente del proyecto se conserva).")
            elif cmd == "/plan":
                if len(parts) < 2:
                    print("Uso: /plan on|off")
                else:
                    orch.plan_mode = parts[1].lower() == "on"
                    print(f"Plan mode: {'ON' if orch.plan_mode else 'OFF'}")
            elif cmd == "/supervision":
                if len(parts) < 2:
                    print("Uso: /supervision on|off")
                else:
                    orch.supervision = parts[1].lower() == "on"
                    print(f"Supervision: {'ON' if orch.supervision else 'OFF'}")
            else:
                print(f"Comando desconocido: '{cmd}'. Usa /help.")
            continue

        if orch.plan_mode:
            print("\n[PLAN MODE] Generando plan...")
            plan_text = orch.generate_plan(user_input)
            print(f"\nPlan propuesto:\n{'-' * 40}\n{plan_text}\n{'-' * 40}")
            approval = input("\nAprobas el plan? [s / modificar / n]: ").strip().lower()

            if approval in ("n", "no"):
                print("Plan rechazado. Ingresa una nueva instruccion.")
                continue
            elif approval not in ("s", "si", "si", "y", "yes", ""):
                modification = input("Describi tu modificacion al plan: ").strip()
                if modification:
                    user_input = f"{user_input}\n\nSegui este plan modificado por el usuario:\n{modification}"

        try:
            response_text = orch.run_turn(user_input)
            print(f"\nAgente:\n{response_text}\n")
        except Exception as e:
            print(f"\nError durante el turno del agente: {e}")
            if orch.messages and orch.messages[-1]["role"] == "user":
                orch.messages.pop()
            raise
        finally:
            flush_observability()


if __name__ == "__main__":
    run_chat()
