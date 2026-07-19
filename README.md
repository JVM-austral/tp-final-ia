# TP Final: Coding Agent Avanzado — NestJS

Sistema multiagente de coding construido desde cero (sin frameworks de orquestación tipo
LangChain/LangGraph/CrewAI) a partir del coding agent del TP de la cursada (`jtvc (2).py`).
Especializado en **NestJS**, con RAG sobre documentación oficial, memoria persistente por
proyecto, subagentes especializados, políticas de seguridad configurables y observabilidad con
Langfuse.

Este README cubre solo instalación, configuración y ejecución. Para el caso de uso, la
arquitectura del sistema multiagente, la documentación del RAG, la evidencia de tareas
ejecutadas, las capturas de observabilidad y la reflexión final, ver [`INFORME_TP.md`](INFORME_TP.md).

## Instalación

Requisitos: Python 3.12, Node.js 20+, npm.

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Instalar también las dependencias del proyecto NestJS objetivo:

```bash
cd workspace/ecommerce-api
npm install
cd ../..
```

## Configuración

1. Copiá `.env.example` a `.env` y completá:
   - `OPENAI_API_KEY` — LLM y embeddings.
   - `TAVILY_API_KEY` — fallback de búsqueda web.
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — observabilidad (cuenta
     gratis en [cloud.langfuse.com](https://cloud.langfuse.com)).
   - `AGENT_MODEL` — modelo de OpenAI a usar. Se recomienda `gpt-5-mini`: con `gpt-5-nano` el
     pipeline de 5 subagentes falla sistemáticamente por agotamiento de iteraciones (detalle en
     [`INFORME_TP.md`, sección 7](INFORME_TP.md#7-reflexión-y-mejoras)).

2. `agent.config.yaml` define el workspace del proyecto objetivo y las políticas de permisos
   (formato del ejemplo de la consigna):

   ```yaml
   workspace: ./workspace/ecommerce-api
   permissions:
     read:
       deny: [".env", ".env.*", "**/*.pem", "**/*.key", "secrets/**", "credentials.json"]
     write:
       deny: [".env", ".env.*", ".github/**", "package-lock.json", "**/*.lock"]
   commands:
     deny: ["rm -rf", "rm -r /", "git push", "git push --force", "sudo", "chmod 777", "shutdown", "reboot"]
     require_approval: ["npm install", "npm uninstall", "npm ci", "git commit", "git add"]
   ```

   Cada tool call (del agente principal y de los subagentes) se valida contra esta configuración
   antes de ejecutarse (`agent/config.py`): sandbox de paths contra `workspace`, deny lists por
   `fnmatch`, y confirmación por consola obligatoria para los comandos en `require_approval`.

### Indexar el RAG (una sola vez, o cuando se actualicen las fuentes)

```bash
python -c "from agent.llm import get_client; from agent.rag.ingest import ingest_directory; print(ingest_directory(get_client()))"
```

Salida esperada: `118` (chunks indexados desde `rag_sources/nestjs/*.md`).

## Ejecución

```bash
python main.py
```

Abre un chat interactivo sobre el proyecto configurado en `agent.config.yaml` (`workspace`).

| Comando | Descripción |
|---|---|
| `/plan on\|off` | Genera un plan y pide aprobación antes de ejecutar |
| `/supervision on\|off` | Confirma herramientas destructivas |
| `/status` | Estado actual de los modos y contador de iteraciones |
| `/clear` | Limpia el historial de la sesión (conserva la memoria persistente del proyecto) |
| `/help` | Ayuda |
| `/exit` | Sale del chat (hace flush de las trazas pendientes a Langfuse) |

La memoria persistente del proyecto vive en `memory_store/<slug-del-workspace>/memory.json` y se
carga automáticamente al arrancar — una sesión nueva no vuelve a explorar el repo desde cero si
ya hay una anterior registrada.
