# NEXUS AI — Local, Repo-Aware Intelligence Core

NEXUS AI is a Windows-first, local-first research and repository intelligence agent. It can learn an entire codebase, learn individual web pages, install reusable skills, answer questions from what it learned, run autonomous research, and switch between four inference engines — including **NEXUS Core** (`nex0.2a`), its own built-in reasoning mode that needs **no Ollama and no model downloads at all**.

Current release: **v0.5.0** (NEXUS Core engine `nex0.2a`).

Everything is stored on your machine in SQLite. NEXUS does not require OpenAI, Anthropic, Google, or any hosted AI API key, and does not consume a hosted provider's token quota. Local models are still constrained by your CPU, RAM, GPU/VRAM and context windows.

## Quick start (Windows 10/11)

1. Install Python 3.10+.
2. Run `start_nexus.bat` and open http://127.0.0.1:8000.
3. That's it. **NEXUS Core works immediately with zero models.** Learn a repository, teach it a web page, browse the 307 offline skills, or queue a research objective right away.
4. Optional: install [Ollama](https://ollama.com/download) and run `install_model.bat` to add generative chat with `qwen2.5:3b` and semantic embeddings with `nomic-embed-text`. You can also point NEXUS at any local OpenAI-compatible server (LM Studio, llama.cpp server, vLLM, Ollama `/v1`).
5. Optional: run `install_autostart.bat` to launch NEXUS when you sign in to Windows. Run `uninstall_autostart.bat` to undo this.

The first launch creates a virtual environment, installs dependencies, initializes/migrates the SQLite database, and recovers interrupted tasks. If auto-resume is enabled and the previous mode was Autonomous or Deep Research, the agent resumes its loop after startup.

## Inference engines

Switch engines any time from the top bar or the **Providers** page. The active engine is used for chat and research generation; NEXUS always retrieves learned repository code and knowledge as context.

| Engine | ID | Needs |
| --- | --- | --- |
| **NEXUS Core** | `nexus` | Nothing. Offline `nex0.2a` reasoning over indexed repos, learned web pages, memories and skills. |
| **Ollama** | `ollama` | Ollama daemon + a pulled chat model. |
| **llama.cpp** | `llamacpp` | `pip install llama-cpp-python` and a local `.gguf` file. |
| **OpenAI-compatible** | `openai` | Any local `/v1` server base URL (LM Studio, vLLM, Ollama `/v1`, llama.cpp server). |

Embeddings also have a fallback chain: Ollama embeddings when available, otherwise a deterministic **local hashing embedder**, so retrieval works even with zero models.

## Learn an entire repository

Open **Repo Lab** and paste one of:

- a GitHub URL (`https://github.com/owner/repo`)
- a shorthand (`owner/repo`)
- a local folder path (`C:\projects\app`)
- a local `.zip` archive

NEXUS downloads the repo zipball (no `git` binary required), walks text files, detects languages and symbols, and stores every file plus **line-addressed chunks** in SQLite. Then:

- browse the file tree and read code in the built-in viewer
- ask questions and get answers grounded in `path:line` evidence
- search across all indexed repos with hybrid semantic + lexical retrieval
- delete an index when you no longer need it

Binaries, vendor folders, `.git`, `node_modules` and oversized files are skipped. Limits (max files, file KB, archive MB, chunk size/overlap) are configurable in **Settings → Repositories**.

Private repos are supported with a GitHub token, which is used only for that download and is never stored.

## Teach NEXUS a web page (URL Learn)

Open **URL Learn** and paste a public HTTPS URL — a greeting guide, a programming tutorial, a library reference, an article. NEXUS fetches the page, checks `robots.txt`, extracts readable text, splits it into overlapping chunks, embeds them and stores everything in SQLite. You can:

- learn one page, or follow one level of same-site links
- use starter packs for **greetings, programming, Python and AI/local models**
- search learned pages by meaning and by keyword
- inspect stored chunks with their source URL
- delete a page and its chunks at any time

URL learning requires the **Internet** permission and is limited to public HTTPS destinations. Only hosts on the configured allow-list are accepted; entries may be hostnames or full URLs (`https://www.wikipedia.org/` becomes `wikipedia.org`). Fetched text is quoted as evidence only — instructions inside a page are never executed or followed.

## Skill Vault (Antigravity)

The **Skills** page ships an offline vault of **307 skills** from the Antigravity skill collection, covering architecture, API design, debugging, security, Python, data, AI, infrastructure and more. Skills are seeded automatically on first start; no internet is required for the built-in snapshot.

- browse, search and filter skills by category and bundle
- open a skill to read its full playbook
- enable or disable skills; disabled skills are excluded from retrieval
- re-import the latest vault from GitHub (`rmyndharis/antigravity-skills`) when internet is enabled
- matching skills are injected into chat as reference guidance only, never as higher-priority instructions

## Write, verify and run programs (Code Studio)

**Code Studio** is a real program forge, not a mock dashboard. Ask for a program in chat or on the page:

- NEXUS first matches the request against **38 offline templates** across Python, JavaScript, PowerShell, HTML and SQL. Templates are complete, runnable programs with built-in self-tests.
- If no template matches, NEXUS can ask a local generative provider (Ollama, llama.cpp/GGUF or an OpenAI-compatible server) for a small program. That output is syntax-checked and labelled **model-generated**; NEXUS never auto-executes it.
- Every generated program is written to `data/programs/<slug>/` inside the app workspace. File names are sanitized, each file is size-capped, and paths cannot escape that folder.
- Verification is evidence-based: Python is compiled in-process, JavaScript is checked with `node --check` when available, and template self-tests must actually exit 0. A program is marked **verified** only when those checks pass.
- Read every file in the built-in viewer, re-run verification, run the program with arguments, preview HTML in a sandboxed iframe, download files, or delete the program.
- Running a program requires the **Run shell commands** permission and is always an explicit action. There is no automatic execution of model output.

Use the **Codegen model** selector to choose a provider for one generation, or set `codegen_provider` in Settings to `auto`, `off`, `ollama`, `llamacpp` or `openai`. Timeouts are configurable with `code_exec_timeout`.

## Permission-gated internet and PC access

NEXUS cannot touch the internet or your PC unless you explicitly grant it in **Permissions**. All four capabilities are **closed by default**:

| Permission | What it allows |
| --- | --- |
| `internet` | Web search and public HTTPS fetch through the crawler. |
| `pc_read` | List folders, read text files, glob search, system info. |
| `pc_write` | Create/overwrite files **inside allowed roots only**. |
| `shell` | PowerShell commands with destructive patterns blocked. |

Additional guards:

- **Allowed roots** restrict all filesystem access to paths you list.
- **Command allow-list** is optional; when set, only listed command prefixes may run.
- A destructive-command deny-list (format, delete, shutdown, pipe-to-shell, etc.) is always applied.
- Every permission change and tool call is written to the **audit log** and visible in the UI.
- Chat can invoke tools through deterministic natural-language intents (e.g. "list files in…", "read…", "run…", "learn this repo…").

Tool console and history are on the Permissions page. Tool runs return structured `{ok, output, error}` results.

## Features

1. **Four-provider architecture** with live online/offline status and per-engine testing.
2. **NEXUS Core offline brain (`nex0.2a`)** — grounded answers from repo chunks, learned web pages, memories and skills, with greetings, identity, follow-up expansion, confidence scoring and no external model.
3. **Repository learning** — GitHub/local/zip ingest, file tree, code viewer, repo-grounded Q&A, hybrid chunk search.
4. **Persistent long-term memory** — SQLite knowledge and experience memories survive restarts; successes and failures are stored as lessons.
5. **Dual embedding retrieval** — Ollama embeddings plus a deterministic local hashing embedder, combined with lexical relevance.
6. **Autonomous, assisted and deep research** — configurable intervals, page budgets and follow-up objectives, with pause/stop.
7. **Automatic research planning** — each objective expands into questions and a persisted plan.
8. **Multi-source verification** — corroborated, disputed, single-source and unclear claim states.
9. **Self-evaluation** — coverage, source diversity and verification produce a quality score and history.
10. **Controlled self-improvement** — improvement proposals with isolated static syntax checks; no automatic production code changes.
11. **Streaming chat** — SSE token streaming, markdown/code rendering, conversation threads and export.
12. **Live activity stream** — WebSocket event feed for research, repo indexing, providers and permissions.
13. **Code-themed UI** — animated NEXUS core with orbital rings, matrix/grid background, terminal aesthetic, responsive layout.
14. **URL learning** — robots-respecting web-page ingest with starter packs, chunk storage, search and per-page delete.
15. **Skill vault** — 307 offline Antigravity skills plus permission-gated GitHub refresh, bundles, toggles and chat guidance.
16. **Program Forge / Code Studio** — 38 offline runnable templates, evidence-based self-test verification, local-model code generation, file viewer, sandboxed HTML preview and explicit program runs.
17. **Scalable retrieval** - two-stage lexical shortlist plus semantic rerank keeps chat fast as the repo index grows past 10,000 chunks; skill vectors are cached.
18. **Auto Programming** - concept seeding across 13 languages, Wikipedia-backed study, sandboxed exercise generation/verification, mastery tracking, difficulty levels and auto-assessment.
19. **Review Studio** - deterministic 8-dimension code scoring, sandboxed run/test, conservative auto-fix, sandboxed CSP preview with console bridge, save/history and ZIP export.
20. **Projects** - 5 archetypes with real file generation, architecture plans, sandbox tests, auto-review and ZIP export.
21. **Code Playground** - multi-language sandboxed execution with per-language examples and self-check.
22. **AI Agents** - seven specialist agents with safe math, cybersecurity refusal policy and team collaboration.
23. **Dashboard** - real-data charts for knowledge growth, programming skills, learning activity, exploration and task completion.
24. **Autonomous exploration** - category discovery, domain allowlist approval, paywall/CAPTCHA detection without bypass.
25. **Self-improvement** - version snapshots, topic normalization, duplicate linking, confidence recomputation and organisation passes.

## Research safety and limits

- Research and URL learning are limited to public HTTPS HTML pages. `robots.txt` is checked and a page is skipped if the check fails or disallows access. URL learning also requires the Internet permission and the configured host allow-list.
- The crawler uses DuckDuckGo HTML search and HTTP/BeautifulSoup extraction, not a full interactive browser.
- It does not bypass logins, paywalls, CAPTCHAs, rate limits or access controls, and does not execute downloaded code.
- Source domains are treated as independent units for corroboration, but ownership/syndication relationships are not independently resolved. A language model can misread evidence; inspect source links, especially for high-stakes decisions.
- NEXUS Core is **extractive** — it quotes and organizes retrieved evidence rather than inventing prose. It is honest about insufficient context, but it is not a general-purpose generative model.
- This is a substantial expanded implementation, not a claim of perfect autonomous intelligence, guaranteed factual correctness, zero bugs, or unlimited context. Test it on your hardware and supervise its research.
- Keep the backend bound to localhost. Do not expose port 8000 publicly without authentication and security hardening.

## Data and privacy

The database lives at `data/nexus.db`; embeddings, repo indexes, learned web pages and the skill vault are stored locally in SQLite. Back up this file before moving or upgrading. Web research, URL learning and repo/skill downloads necessarily send ordinary HTTP requests to public sources. Chat prompts and local memory are sent only to the engine you selected — and NEXUS Core sends nothing off the machine.

## Developer run

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Optional generative engines:

```powershell
# Ollama
ollama serve
ollama pull qwen2.5:3b
ollama pull nomic-embed-text

# Embedded llama.cpp
pip install llama-cpp-python
# then set the GGUF path in Providers → Engine configuration
```

## Important endpoints

- `GET /api/status`, `GET /api/hardware`, `GET /api/stats`, `GET /api/export`
- `GET /api/providers`, `POST /api/providers/select`, `POST /api/providers/test`
- `GET /api/models`, `POST /api/models/pull`
- `POST /api/repos/ingest`, `GET /api/repos`, `GET /api/repos/{id}`
- `GET /api/repos/{id}/file?path=...`, `DELETE /api/repos/{id}`, `POST /api/repos/search`
- `POST /api/learn/url`, `GET /api/learn/url`, `GET|DELETE /api/learn/url/{id}`, `POST /api/learn/url/search`
- `GET /api/learn/packs`, `POST /api/learn/pack`
- `GET /api/skills`, `GET /api/skills/stats`, `GET|DELETE /api/skills/{id}`, `POST /api/skills/{id}/toggle`
- `POST /api/skills/import`, `POST /api/skills/seed`, `GET /api/skills/imports`, `POST /api/skills/search`
- `POST /api/chat`, `POST /api/chat/stream` (SSE)
- `GET /api/conversations`, `GET|DELETE /api/conversations/{id}`, `POST /api/conversations/{id}/rename`
- `POST /api/tasks`, `GET /api/tasks/{id}/plan`, `POST /api/agent/start|pause|resume|stop`
- `GET /api/knowledge`, `GET /api/knowledge/search?q=...`, `DELETE /api/knowledge/{id}`
- `GET /api/memory`, `DELETE /api/memory/{id}`, `POST /api/search`
- `GET /api/claims`, `GET /api/evaluations`, `GET /api/events`
- `GET /api/proposals`, `POST /api/proposals/{id}/decision`, `POST /api/proposals/{id}/sandbox-test`
- `GET /api/programs`, `GET /api/programs/recipes`, `POST /api/programs/detect`, `POST /api/programs/generate`
- `GET|DELETE /api/programs/{id}`, `GET /api/programs/{id}/file?name=...`, `GET /api/programs/{id}/raw/{name}`
- `POST /api/programs/{id}/verify`, `POST /api/programs/{id}/run`
- `GET /api/experiments`, `GET|POST /api/settings`
- `GET /api/dashboard`, `GET /api/dashboard?days=30`
- `GET /api/autoprogramming/status`, `POST /api/autoprogramming/study`, `GET /api/autoprogramming/concepts`, `GET /api/autoprogramming/exercises`, `POST /api/autoprogramming/exercises/{id}/run`, `POST /api/autoprogramming/start|pause|resume|stop`
- `POST /api/review/analyze`, `POST /api/review/run`, `POST /api/review/fix`, `POST /api/review/preview`, `POST /api/review/save`, `GET /api/review/history`, `POST /api/review/export`
- `POST /api/projects`, `GET /api/projects`, `GET|DELETE /api/projects/{id}`, `POST /api/projects/{id}/test`, `POST /api/projects/{id}/review`, `POST /api/projects/{id}/export`
- `POST /api/playground/run`, `GET /api/playground/self-check`, `GET /api/playground/meta`
- `GET /api/agents`, `POST /api/agents/run`, `POST /api/agents/team`, `GET /api/agents/runs`, `GET /api/agents/stats`
- `GET /api/explore/stats`, `GET /api/explore/allowlist`, `POST /api/explore/approve`, `POST /api/explore/discover`, `POST /api/explore/url`, `POST /api/explore`
- `POST /api/assessments`, `GET /api/assessments`, `POST /api/assessments/{id}/solve`, `GET /api/assessments/{id}/compare`, `GET /api/assessments/stats`
- `GET /api/self-improve/stats`, `POST /api/self-improve/organize`, `GET /api/self-improve/versions/{id}`, `GET /api/self-improve/explain/{id}`
- `GET /api/tools`, `POST /api/tools/run`, `GET|POST /api/permissions`, `GET /api/audit`, `GET /api/tool-runs`
- `WS /ws`
