# Local AI Platform Plan

This document defines how this Odysseus fork evolves into a local-first AI workspace with ChatGPT/Claude-style chat, research, coding, memory, RAG, tool use, model routing, and secure autonomous execution.

## Architecture decision

Do **not** create a second application or replace Odysseus' existing runtime. Extend the current architecture and keep the existing model, tool, security, session, research, memory, RAG, MCP, context-management, and UI systems authoritative.

```text
UI / Chat / Workspace
        |
        v
Intent + Mode Activation
(chat / research / coding / documents)
        |
        v
Existing Agent Runtime + Specialized Controllers
        |
        +--> Coding Agent controller
        +--> Research controller
        +--> Document / RAG controller
        |
        v
Existing Model Resolution + Capability Metadata
        |
        +--> Ollama
        +--> llama.cpp / LM Studio
        +--> OpenAI-compatible / vLLM / SGLang
        +--> OpenRouter / OpenAI / Google / other configured endpoints
        |
        v
Existing Tool Dispatcher
        |
        +--> filesystem / git / shell
        +--> web / research
        +--> MCP
        +--> memory / RAG
        +--> sessions / model-to-model tools
        |
        v
Security + Approvals + Workspace Confinement
```

The existing dispatcher and security policy remain the only path to privileged tools.

## Existing components to reuse

### Model/provider and capability layer

Reuse Odysseus' endpoint configuration, `_resolve_model`, `endpoint_resolver`, `llm_core`, `foreground_model_routing`, `model_context`, and the existing `src/model_capabilities.py` system. Do not create a second capability registry.

The existing capability system already models families, modalities, capabilities such as tool calling/reasoning/vision/structured output, source/confidence, capability assertions, deterministic controls, and capability probes. Vendor readers already exist for Ollama, llama.cpp, LM Studio, OpenAI, OpenRouter, Google, and generic OpenAI-compatible endpoints.

The Coding and Research controllers should consume this capability metadata to choose safe execution strategies. Unknown or weak model capabilities must degrade conservatively.

### Agent runtime

Reuse `src/agent_loop.py`, the current tool execution pipeline, session state, owner/security context, exact approvals, and tool policy. Specialized modes are controllers that compose with this runtime, not independent agents with unrestricted execution.

### Coding Agent

Reuse and extend `src/coding_agent/`. It already contains bounded autonomous iteration, task state, provider-neutral model access, repository context selection, test detection, Git inspection, approval/autonomy policy, UI lifecycle events, a secured dispatcher bridge, and an end-to-end test/fix/review workflow.

### Research

Reuse `src/deep_research.py`, `src/research_handler.py`, the research routes, and existing search tools. Add deterministic source ledgers, persistent research task state, contradiction/freshness handling, and stronger source-grounded synthesis instead of creating a parallel search stack.

### Context management

Reuse `src/context_budget.py`, `src/context_compactor.py`, and `src/model_context.py`. Coding/research-specific context selectors should feed these systems rather than implementing a separate long-context framework.

### Memory and RAG

Reuse `src/memory.py`, `memory_provider.py`, `memory_vector.py`, `rag_manager.py`, `rag_vector.py`, `personal_docs.py`, existing embeddings infrastructure, and document ingestion. Add explicit scopes and a common retrieval facade where needed rather than replacing storage.

Memory scopes should become explicit:

- session/task state
- project/workspace memory
- user memory

Sensitive repository content must not automatically become long-term user memory.

### MCP, tools, and security

Reuse the tool registry, MCP manager, `tool_execution.py`, `tool_policy.py`, `tool_security.py`, approvals, prompt-security helpers, URL safety, and secret storage. Third-party MCP output and repository/web/document content remain untrusted data and cannot expand tool authority.

### UI

Reuse the existing chat UI and status stream. Specialized modes add status cards, source panels, plans, diff summaries, and approval prompts without introducing a second frontend framework.

## Target modes

### Chat

- streaming conversation
- local/cloud models
- files and attachments
- memory
- tool use
- model switching/fallback

### Coding Agent

- inspect/search first
- targeted edits and patches
- shell/test/build execution
- failure recovery
- Git review
- Safe / Balanced / Autonomous policy
- optional commit; push separately gated

### Research

- question decomposition
- multi-query search
- source opening/extraction
- source ledger
- publication date/freshness
- contradiction handling
- primary-source preference
- cited reports

### Document Q&A / local knowledge

- PDF / Markdown / TXT / DOCX / code / JSON / CSV / HTML
- incremental indexing
- metadata-aware retrieval
- hybrid/vector retrieval using existing infrastructure
- local embeddings where configured

## Security architecture

Trust order:

```text
system/security policy
    > user instruction
    > task/mode policy
    > tool policy
    > repository/web/document/MCP/tool output
```

Repository files, README instructions, issue text, webpages, documents, command output, and MCP responses are untrusted content.

Default-deny or approval-gate access to `.env`, private keys, cloud credentials, browser/session credentials, credential stores, API secrets, and system paths outside the selected workspace.

Autonomy modes remain:

- **Safe** — inspect/search/read; approval before edits or shell mutation.
- **Balanced** — edit workspace files and run normal development commands; approval for sensitive/destructive/external actions.
- **Autonomous** — independent work within configured limits; secrets, destructive operations, pushes, external side effects, and security-sensitive changes remain approval-gated.

## Model execution strategy

The existing `ModelCapability` metadata is the canonical capability source. Specialized agents need a small policy adapter that converts capability evidence into an execution strategy:

- `native_tools` — use structured/native tool calling only when explicitly/provider-reported/verified support is sufficiently trustworthy.
- `text_tools` — use Odysseus' fenced/text tool protocol when native tools are unavailable or uncertain.
- `chat_only` — do not activate autonomous tool use for incompatible model families such as embeddings/image-only models.

Capability metadata grants **no authority**. Tool execution still passes through normal security and approvals.

## Research task design

Research should gain persistent state analogous to Coding Agent state:

```text
request
subquestions
queries
sources[]
claims[]
contradictions[]
remaining_questions[]
limits
status
```

Each source record should track title, URL, publisher/domain, publication date when known, source type, retrieval time, originating query, relevance, reliability hint, and notes. The model may synthesize source content but must never invent citations or ledger entries.

## RAG / memory design

Keep existing managers and add a common controller-facing retrieval facade if needed:

```text
KnowledgeSearch
  search(query, scope, filters, limit)
  ingest(source)
  refresh(source)
  source_info(id)
```

Scopes: current session, selected workspace, personal documents, explicit user memory. File hashes and metadata should prevent unnecessary re-indexing.

## UI design

The existing chat remains primary. Add/continue explicit mode surfaces for Chat, Research, Coding Agent, and Document Q&A. Show task, current phase, plan summary, tool activity, test/build state, research source count/citations, approvals, and final diff/source summary. Never expose private chain-of-thought.

## Implementation phases

### Phase 1 — Architecture and capability audit

- document authoritative existing systems
- identify already-existing capability/context/research/memory infrastructure
- define mode boundaries and acceptance tests
- avoid duplicate frameworks

**Exit:** architecture documented; regression suite green.

### Phase 2 — Capability-aware agent execution

- build a thin policy adapter over existing `ModelCapability`
- choose native-tools vs text-tools vs chat-only safely
- integrate it first with Coding Agent model execution
- gracefully handle weak local models
- add tests for tool-capable, unknown, embedding, and local/fallback cases

### Phase 3 — Coding Agent live product integration

- finish deterministic activation in normal chat/workspace flow
- make the bounded autonomous controller reachable from the normal UI path
- expose plan/status/tool activity
- resume persisted tasks
- preserve dispatcher/security authority

### Phase 4 — Research Agent upgrade

- persistent research task state
- source ledger
- query planning
- contradiction/freshness handling
- cited synthesis
- end-to-end research test

### Phase 5 — Knowledge/RAG facade

- unify controller-facing local knowledge retrieval
- user/session/workspace scoping
- hash-aware incremental indexing
- reuse current vector/embedding infrastructure

### Phase 6 — Project memory

- workspace-scoped facts and conventions
- inspect/edit/delete controls
- no implicit secret or repository-content persistence

### Phase 7 — Shared context policy

- integrate coding/research context with existing budget/compaction systems
- changed-file/tool-result caching
- deduplication
- large-file/source summarization

### Phase 8 — UI mode polish

- explicit mode selector
- research source panel
- coding plan/diff/test status
- approval UX
- cancel/resume

### Phase 9 — Hardening

- prompt-injection regressions
- secret/path confinement
- MCP trust boundaries
- destructive commands
- cross-user/session isolation

### Phase 10 — End-to-end local assistant validation

Acceptance scenario:

> Research FastAPI authentication best practices, then build a FastAPI application using those findings, add PostgreSQL, Docker and tests.

Required flow:

```text
research -> plan -> inspect -> code -> test -> fix -> review -> sourced completion
```

## Acceptance requirements

The platform is done only when local Ollama models participate through the same model abstraction, strong models can run bounded agent workflows, weak models degrade safely, research citations are verifiable, coding tasks cannot claim success with relevant failing tests, all privileged actions remain behind Odysseus security/approval/workspace boundaries, memory/task state is inspectable, and the full regression suite remains green.

## Immediate implementation target

Implement the thin **capability-aware agent policy adapter** over the already-existing `src/model_capabilities.py` system, then wire it into Coding Agent model selection without changing provider configuration or tool authority.
