# Local AI Platform Plan

This document defines how the Odysseus fork evolves into a local-first AI workspace with ChatGPT/Claude-style chat, research, coding, memory, RAG, tool use, model routing, and secure autonomous execution.

## 1. Architecture decision

Do **not** create a second application or replace Odysseus' existing runtime. Extend the current architecture and keep the existing model, tool, security, session, research, memory, RAG, MCP, and UI systems authoritative.

The target architecture is:

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
Shared Model Abstraction
        |
        +--> Ollama
        +--> OpenAI-compatible
        +--> OpenRouter
        +--> Anthropic
        +--> other configured Odysseus endpoints
        |
        v
Shared Tool Dispatcher
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

## 2. Existing components to reuse

### Model/provider layer

Reuse Odysseus' existing endpoint configuration, `_resolve_model`, endpoint resolver, and `llm_core` rather than introducing another provider registry. The current system already resolves configured local and remote endpoints and routes requests through provider-neutral call paths.

The Coding Agent must continue using the same model resolution path. Model capability metadata should be layered on top of the existing endpoint records instead of replacing them.

### Agent runtime

Reuse `src/agent_loop.py`, the current tool execution pipeline, session state, owner/security context, exact approvals, and tool policy. Specialized modes should be controllers that compose with this runtime, not independent agents with unrestricted execution.

### Coding Agent

Reuse the existing `src/coding_agent/` package and extend it. It already provides task state, bounded autonomous iteration, provider-neutral model access, repository context selection, test detection, Git inspection, approvals/autonomy policy, UI lifecycle events, and the secured dispatcher bridge.

### Research

Reuse the existing research routes and web/research tooling. Research work should add deterministic source tracking, research plans, evidence quality metadata, contradiction handling, and source-led synthesis rather than building a separate search stack.

### Memory and RAG

Reuse the existing memory manager, vector memory, RAG manager, personal documents manager, and document ingestion paths. Add scoping and retrieval policy where needed rather than replacing storage.

Memory scopes should become explicit:

- session/task state
- project/workspace memory
- user memory

Sensitive repository content must not automatically become user long-term memory.

### MCP and tools

Reuse the current tool registry and MCP integration. Third-party MCP output and repository/web content remain untrusted data and cannot expand tool authority.

### UI

Reuse the existing chat UI and status stream. Specialized modes should add status cards, source panels, plans, diff summaries, and approval prompts without introducing a second frontend framework.

## 3. Target capabilities

### General assistant

- streaming chat
- local and cloud models
- files and attachments
- memory
- sessions
- tool use
- model switching
- long-context management

### Coding

- repository inspection
- search-first context selection
- targeted edits
- shell/test/build execution
- test failure recovery
- Git review
- Safe / Balanced / Autonomous policy
- optional commit, push always separately gated

### Research

- question decomposition
- multi-query search
- source opening and extraction
- source ledger
- reliability/source-type metadata
- dates and freshness
- contradiction detection
- primary-source preference
- cited final reports

### Local knowledge / RAG

- PDF / Markdown / TXT / DOCX / code / JSON / CSV / HTML ingestion
- incremental indexing
- file hash based change detection
- hybrid retrieval
- metadata-aware ranking
- optional reranking
- local embeddings where configured

### Context management

- search before read
- file/section relevance ranking
- bounded tool-result retention
- unchanged-file caching by hash
- conversation/task summaries
- no full-repository dumping

## 4. Security architecture

Security is layered and deny-by-default for privileged actions.

### Trust order

```text
system/security policy
    > user instruction
    > task/mode policy
    > tool policy
    > retrieved repository/web/document/MCP content
```

Repository files, README instructions, issue text, web pages, documents, command output, and MCP responses are untrusted content.

### Protected data

Default-deny or approval-gate access to:

- `.env`
- SSH/private keys
- cloud credentials
- browser/session credentials
- credential stores
- API secrets
- system directories outside the workspace

### Autonomy

Safe:
- inspect/search/read
- approval before edits or shell mutation

Balanced:
- edit workspace files
- run normal development commands/tests
- approval for destructive/sensitive/external actions

Autonomous:
- run independently within configured limits
- destructive operations, secrets, pushes, external side effects, and security-sensitive changes remain approval-gated

## 5. Model capability design

Add a lightweight capability profile around existing model endpoints. It should answer:

- native tool calling supported?
- fallback structured/text tool protocol available?
- vision supported?
- context-window estimate?
- embedding model?
- local vs remote?
- recommended task classes: chat / code / research / summarization / embeddings

This metadata must be optional and backwards compatible. Unknown capability values should degrade safely instead of blocking model use.

The first implementation should consume the existing endpoint configuration and explicit `supports_tools` setting where available.

## 6. Research design

Research gets a persistent task state similar in spirit to coding tasks:

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

A source record should include at least:

```text
title
url
publisher/domain
published_at (when known)
source_type
retrieved_at
query
relevance
reliability_hint
notes
```

The model may synthesize from source content but must never invent ledger entries or citations.

## 7. RAG / memory design

Keep current managers, but introduce a retrieval facade so agents do not need to know storage implementation details.

```text
KnowledgeSearch
  search(query, scope, filters, limit)
  ingest(path/source)
  refresh(source)
  source_info(id)
```

Scopes:

- current session
- selected workspace/project
- personal documents
- explicit user memory

File hashes and document metadata should prevent unnecessary re-indexing.

## 8. UI design

The existing chat remains the primary interface.

Add/continue mode surfaces for:

- Chat
- Research
- Coding Agent
- Document Q&A

Visible agent information should include:

- task
- current phase
- plan summary
- tool activity
- tests/build status
- source count and citations for research
- approval requests
- final diff/source summary

Never render private chain-of-thought.

## 9. Implementation phases

### Phase 1 — Architecture and capability audit

- document authoritative existing systems
- identify duplicated/parallel paths
- define mode boundaries
- define model capability metadata
- define acceptance tests for each mode

**Exit:** architecture documented; full existing test suite still green.

### Phase 2 — Model capability layer

- add provider-neutral capability profile
- detect/use endpoint `supports_tools`
- expose safe capability queries to controllers/UI
- graceful fallback for weak local models
- tests for local/OpenAI-compatible/unknown models

### Phase 3 — Coding Agent live product integration

- finish deterministic activation in normal chat/workspace flow
- make live autonomous controller execution reachable from UI
- preserve dispatcher/security path
- expose plan/status/tool activity
- resume persisted tasks

### Phase 4 — Research Agent upgrade

- research task state
- source ledger
- query planning
- contradiction/freshness handling
- cited final synthesis
- end-to-end research test

### Phase 5 — Knowledge/RAG facade

- unify local document retrieval API
- scope by user/session/workspace
- incremental/hash-aware indexing
- hybrid retrieval where existing infrastructure supports it

### Phase 6 — Project memory

- workspace-scoped facts and conventions
- explicit inspect/edit/delete UI/API
- no implicit secret/repository-content persistence

### Phase 7 — Context manager

- shared context budget
- changed-file cache
- tool-result deduplication
- large-file summaries
- source/file priority policy

### Phase 8 — UI mode polish

- explicit mode selector
- research source panel
- coding plan/diff/test status
- approval UX
- cancel/resume

### Phase 9 — Hardening

- prompt-injection regression suite
- secret/path confinement suite
- MCP trust-boundary suite
- destructive command coverage
- cross-user/session isolation

### Phase 10 — End-to-end local assistant validation

Acceptance scenario:

> Research FastAPI authentication best practices, then build a FastAPI application using those findings, add PostgreSQL, Docker and tests.

Required flow:

```text
research -> plan -> inspect -> code -> test -> fix -> review -> sourced completion
```

## 10. Acceptance requirements

The platform is not done when it only generates good text. It is done when:

- local Ollama models can participate through the same model abstraction
- strong tool-capable models can execute bounded autonomous tasks
- weak models degrade gracefully instead of being given unsafe authority
- research outputs have verifiable citations
- coding tasks cannot claim success while relevant tests fail
- all privileged tools still pass through Odysseus security/approval/workspace boundaries
- users can inspect and control persisted memory/task state
- the full Odysseus regression suite remains green

## 11. Immediate next implementation target

Phase 2 should begin by implementing a **model capability profile** that reuses existing model endpoint records and the current model resolver. This is the prerequisite for safely deciding whether a selected local model should receive native tools, text/fenced tool fallback, or non-agent chat behavior.
