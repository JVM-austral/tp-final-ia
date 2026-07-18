# TP Final: Coding Agent Avanzado — NestJS

Sistema multiagente de coding construido desde cero (sin frameworks de orquestación tipo
LangChain/LangGraph/CrewAI) a partir del coding agent del TP de la cursada (`jtvc (2).py`).
Especializado en **NestJS**, con RAG sobre documentación oficial, memoria persistente por
proyecto, subagentes especializados, políticas de seguridad configurables y observabilidad con
Langfuse.

## Instalación

Requisitos: Python 3.12, Node.js 20+, npm.

```bash
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

## Configuración

1. Copiá `.env.example` a `.env` y completá:
   - `OPENAI_API_KEY` — LLM y embeddings.
   - `TAVILY_API_KEY` — fallback de búsqueda web.
   - `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_HOST` — observabilidad (cuenta
     gratis en [cloud.langfuse.com](https://cloud.langfuse.com)).
   - `AGENT_MODEL` — modelo de OpenAI a usar (ver [Reflexión](#reflexión) sobre por qué se usa
     `gpt-5-mini` en vez de `gpt-5-nano`).
2. `agent.config.yaml` define el workspace del proyecto objetivo y las políticas de permisos
   (ver [Políticas y guardrails](#políticas-y-guardrails)).

### Indexar el RAG (una sola vez, o cuando se actualicen las fuentes)

```bash
python -c "from agent.llm import get_client; from agent.rag.ingest import ingest_directory; print(ingest_directory(get_client()))"
```

## Ejecución

```bash
python main.py
```

Abre un chat interactivo sobre el proyecto configurado en `agent.config.yaml` (`workspace`).
Comandos disponibles: `/plan on|off`, `/supervision on|off`, `/status`, `/clear`, `/help`,
`/exit`.

## Caso de uso

**Proyecto**: `workspace/ecommerce-api`, una API NestJS de e-commerce armada para este TP,
con un módulo `Products` (CRUD in-memory, DTOs con `class-validator`) ya implementado como
convención existente.

**Objetivo concreto**: que el agente agregue un módulo `Orders` completo (controller, service,
DTOs, module) relacionado a `Products` (`productId`), siguiendo exactamente las convenciones
del módulo existente, y que sea capaz de iterar sobre ese módulo en sesiones posteriores
(agregar campos, endpoints) reusando memoria persistente en vez de re-explorar todo el repo.

**Criterio de cumplimiento**: `npm run build` y `npm test` pasan después de cada cambio, el
código generado sigue el patrón de `Products` (mismo estilo de DTOs, mismo manejo de
`NotFoundException`, mismo uso de `ParseIntPipe`/`ParseEnumPipe`), y las fuentes usadas por el
agente (repo, RAG, memoria, web) quedan explícitas en su respuesta final.

## Arquitectura

### Agente principal (`agent/orchestrator.py`)

Mantiene el `TaskState` de la tarea en curso, arma el system prompt con un resumen de la
memoria persistente del proyecto, y decide entre resolver algo con sus propias tools de
lectura (`read_file`, `run_command`, `list_files`, `web_search`) o delegar en un subagente.
**No tiene `write_file`**: cualquier cambio de código pasa obligatoriamente por
`delegate_to_implementer`, así que la arquitectura multiagente no es opcional aunque el modelo
"quiera" resolver todo por su cuenta. Aplica guardrails (`agent/config.py`) a cada tool call,
detecta loops (`agent/context.py`) y resume el historial cuando crece demasiado.

### Subagentes (`agent/subagents/`)

Cada uno corre su **propio** loop de tool-calling (mensajes, herramientas y presupuesto de
iteraciones independientes del agente principal), y al terminar reporta un resultado
estructurado (`status: done|blocked`, `summary`, `findings`, `sources`) que se guarda en el
`TaskState` compartido.

| Subagente | Responsabilidad | Tools |
|---|---|---|
| Explorer | Estructura del repo, convenciones, archivos relevantes | `read_file`, `list_files`, `run_command`, `rag_search` |
| Researcher | RAG de NestJS primero, web como fallback | `rag_search`, `web_search`, `read_file` |
| Implementer | Único con permiso de escritura | `read_file`, `write_file`, `list_files`, `rag_search` |
| Tester | `build`/`test`/`lint`, no modifica código | `run_command`, `read_file` |
| Reviewer | Valida el resultado contra el pedido original | `read_file`, `run_command` |

Un subagente que no tiene evidencia suficiente (pedido ambiguo, cambio riesgoso, no llegó a
terminar) devuelve `status=blocked` con el motivo en `missing`, en vez de inventar una
respuesta. El agente principal, al recibir `blocked`, no reintenta a ciegas: se lo explica al
usuario y pide una decisión (ver [evidencia](#evidencia-de-tareas-ejecutadas), corridas 1 y 3).

### Estado compartido (`agent/state.py`)

`TaskState` por turno: pedido original, progreso (`log_progress`), resultado de cada subagente,
`sources_consulted` (con `kind` ∈ `repo|memory|rag|web|inference`), `files_modified`,
`observations`, contador de iteraciones y de warnings de loop. Se persiste a
`memory_store/<slug>/last_task_state.json` al final de cada turno.

### Memoria persistente (`agent/memory.py`)

`memory_store/<slug del workspace>/memory.json`: arquitectura detectada, archivos importantes,
dependencias, comandos útiles, convenciones, decisiones, bugs investigados y resúmenes de
sesión. Se carga al arrancar `main.py` y se inyecta **resumida** (no el JSON completo) en el
system prompt del agente principal — así una sesión nueva no vuelve a explorar el repo desde
cero (ver evidencia, corrida 2).

Nota de implementación: como `main.py` hace `os.chdir()` al workspace del proyecto objetivo
para que las tools de archivos operen ahí con paths relativos, tanto `memory_store/` como el
índice RAG (`rag_sources/chroma_db/`) están anclados a la raíz de este proyecto vía
`agent/paths.py`, independientes del `cwd` — si no, terminarían escribiéndose dentro del repo
del usuario.

## RAG

**Fuentes**: 9 páginas de la documentación oficial de NestJS (código fuente markdown del repo
`nestjs/docs.nestjs.com`, no HTML scrapeado — el sitio es una SPA sin contenido en el HTML
crudo): `first-steps`, `controllers`, `providers`, `modules`, `pipes`, `validation`,
`exception-filters`, `guards`, `unit-testing`. Guardadas en `rag_sources/nestjs/*.md`.

**Chunking** (`agent/rag/ingest.py`): cada doc se parte primero por sus headers de markdown
(`##`–`####`), preservando la ruta de títulos como contexto (ej. `pipes > Class validator`);
cada sección se subdivide en ventanas de ~500 tokens con 50 de solapamiento (`tiktoken`,
encoding `cl100k_base`) para no cortar ideas ni generar chunks gigantes. Resultado: 118 chunks.

**Embeddings**: OpenAI `text-embedding-3-small`.

**Almacenamiento**: ChromaDB persistente local (`rag_sources/chroma_db/`), espacio de
similaridad coseno.

**Uso**: la tool `rag_search` (disponible para Explorer, Researcher e Implementer) devuelve los
top-k chunks con su fuente y score, y registra el evento en Langfuse (`rag:retrieval`). Si el
mejor score está por debajo de `MIN_RELEVANCE_SCORE=0.25`, el resultado incluye una advertencia
sugiriendo `web_search` como fallback — así el Researcher prioriza RAG > web > inferencia
propia, como pide la consigna.

## Políticas y guardrails

`agent.config.yaml` (formato del ejemplo de la consigna) valida **cada** tool call, del agente
principal y de los subagentes, antes de ejecutarla (`agent/config.py`):

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

Además del sandbox (todo path se resuelve contra `workspace` y se rechaza si cae afuera), los
comandos en `require_approval` piden confirmación por consola **siempre**, esté o no activado
el modo supervisión general (`/supervision on`).

## Evidencia de tareas ejecutadas

Salida completa de terminal en [`evidence/`](evidence/):

### 1. [`run1_rag_task.txt`](evidence/run1_rag_task.txt) — tarea con RAG

Pedido: agregar el módulo `Orders` completo. Recorre **Explorer → Researcher → Implementer →
Tester** (10 iteraciones totales de este turno). El Researcher consulta `rag_search` (fuente
`pipes > Binding pipes`, `validation`, etc.) antes de proponer los decoradores de
`class-validator`; el resultado final lista explícitamente las fuentes usadas por cada
subagente (`fuente [repo]: ...`, `fuente [rag]: NestJS docs: pipes`). El Tester detecta
correctamente que un fallo de lint es preexistente y no de los archivos que tocó, y pide
autorización antes de tocar código fuera de su tarea en vez de asumir. Build y tests pasan
sobre el módulo `Orders` generado (6 archivos: `orders.module.ts`, `orders.controller.ts`,
`orders.service.ts`, `entities/order.entity.ts`, `dto/create-order.dto.ts`,
`dto/update-order.dto.ts`).

### 2. [`run2_memory_task.txt`](evidence/run2_memory_task.txt) — tarea con memoria

Proceso **nuevo** (sesión distinta). Al arrancar, la consola muestra "Memoria persistente
cargada para este proyecto" con la arquitectura, archivos y convenciones detectadas en la
corrida anterior — no vacío. Pedido: agregar un campo opcional `notes` al DTO de `Orders`.
Corre el flujo completo hasta **Reviewer** (`status=done`), que valida que el cambio siga el
patrón de `Products`/`Orders` y no rompa nada.

### 3. [`run3_loop_task.txt`](evidence/run3_loop_task.txt) — repetición sin avance

Se le pide al agente ejecutar tres veces seguidas un comando que siempre falla igual
(`ls carpeta_que_no_existe_12345`). El `LoopDetector` (`agent/context.py`) detecta la 3ª
repetición idéntica (misma tool, mismos args, mismo resultado) e inyecta una advertencia en el
resultado de la tool; el agente la traslada al usuario ("el sistema detectó que se repitió la
misma acción...") y ofrece alternativas en vez de seguir reintentando a ciegas.

### 4. [`run4_langfuse_trace.txt`](evidence/run4_langfuse_trace.txt) — traza completa en Langfuse

Agrega un endpoint `GET /orders/status/:status` (Explorer → Researcher, con `rag_search` sobre
`pipes > Binding pipes` para `ParseEnumPipe` → Implementer → Tester, build y tests OK). Esta
corrida generó el trace de Langfuse referenciado abajo (proceso cortado por timeout de la
terminal ya con el cambio aplicado y verificado; Langfuse igual capturó el trace completo por
el flush en background del SDK — ver [Observabilidad](#observabilidad)).

## Observabilidad

Langfuse instrumenta automáticamente cada llamada al LLM (`langfuse.openai.OpenAI` como
reemplazo directo del cliente de OpenAI en `agent/llm.py`: prompt, modelo, tokens, latencia,
costo) y, vía `agent/observability.py`, anida como spans cada subagente (`@observe`) y registra
como eventos las tool calls (`log_tool_call`) y las recuperaciones de RAG (`log_retrieval`).

El trace de la corrida 4 (`evidence/run4_langfuse_trace.txt`) quedó registrado con **108
observaciones**: spans `subagent:explorer/researcher/implementer/tester`, **51 llamadas al LLM**
(`gpt-5-mini`, con tokens de input/output por llamada), eventos `tool:*` por cada tool call, y
eventos `rag:retrieval` con las fuentes recuperadas.

**Capturas de pantalla**: <!-- TODO: pegar acá las capturas del dashboard de Langfuse —
Tracing > Traces > abrir el trace del 2026-07-14 ~00:54 UTC. Sugerido: (a) el árbol de spans
completo, (b) una GENERATION expandida con prompt/modelo/tokens, (c) un evento rag:retrieval
expandido con las fuentes. -->

## Reflexión

**Qué funcionó bien**: la separación de tools por subagente (solo Implementer escribe) obliga
estructuralmente a usar la arquitectura multiagente en vez de que el modelo resuelva todo por
su cuenta. El mecanismo de `status=blocked` + guardrails de `require_approval` produjo varios
casos reales (no forzados) de "el agente pide ayuda en vez de asumir": el Tester se negó a
tocar archivos fuera de su tarea, y en una corrida temprana el propio orquestador frenó a pedir
una decisión de diseño (validar `productId` contra `ProductsService` o no) en vez de adivinar.

**Qué falló / limitaciones encontradas**:
- Con `gpt-5-nano` (el modelo original de la cursada) el pipeline de 5 subagentes fallaba
  sistemáticamente: se quedaba sin iteraciones antes de llamar a `submit_result`, y en una
  corrida multi-turno llegó a inventar campos (`customerName`, `total`) que no se habían
  pedido, perdiendo el detalle del pedido original entre delegaciones. Se subió a `gpt-5-mini`
  (mismo proveedor, un salto de capacidad) y el pipeline completo empezó a cerrar de forma
  confiable.
- Bug real encontrado y corregido: `os.chdir()` al workspace del proyecto objetivo hacía que
  rutas relativas propias del agente (`memory_store/`, `rag_sources/chroma_db/`) se resolvieran
  **dentro del repo del usuario** en vez de en la raíz del agente — se corrigió anclándolas
  explícitamente (`agent/paths.py`).
- Bug real encontrado y corregido: un tool call con argumentos alucinados por el modelo (un
  parámetro inexistente) tiraba abajo todo el proceso con `TypeError` sin manejar — se agregó
  try/except alrededor de cada ejecución de tool.
- El `LoopDetector` compara el resultado completo de la tool como string; comandos como
  `npm run <script inexistente>` incluyen un timestamp en la ruta del log de error, así que
  "el mismo fallo" no siempre produce el mismo string y el detector no dispara. Se comprobó con
  un comando de resultado 100% determinístico. Mejora pendiente: normalizar/limpiar el
  resultado (o comparar solo el `tool_name` + código de retorno) antes de hashear.
- Los subagentes son stateless entre sí (solo reciben un `instruction` de texto del
  orquestador), lo que los lleva a re-leer archivos que otro subagente ya leyó — genera gasto
  de iteraciones. Mejora pendiente: pasarles un resumen estructurado de hallazgos previos en
  vez de solo texto libre.

**Qué mejoraríamos**: pasar hallazgos estructurados (no solo texto) entre subagentes; afinar el
`LoopDetector` para que no dependa de igualdad exacta de strings; agregar tests automáticos
generados por el propio Implementer/Tester para el código nuevo (hoy el Reviewer nota que
faltan tests para `Orders`, pero nadie los agrega automáticamente); costo estimado en Langfuse
no se calculó para `gpt-5-mini` (tabla de precios desactualizada en el SDK) — habría que
configurarlo manualmente.

## Extra opcional

No implementado en esta entrega: sistema de plugins para tools (las tools están registradas de
forma estática en `agent/tools/registry.py`).
