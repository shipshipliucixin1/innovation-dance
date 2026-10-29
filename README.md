# ProjectFlow

**AI-native Workspace for Learning, Thinking, Building and Collaborating**

A local workspace for creators in any field. Bring an unfinished idea, explore it through lightweight thinking prompts, turn it into a small experiment, delegate a concrete task, and return with evidence. Share a deliberately selected public snapshot when you want collaborators.

[中文说明](README.zh-CN.md) · [5-minute demo](DEMO_GUIDE.md) · [Development report](docs/DEVELOPMENT_REPORT.md) · [Contributing](CONTRIBUTING.md)

Source repository: [shipshipliucixin1/innovation-dance](https://github.com/shipshipliucixin1/innovation-dance). The repository name is `innovation-dance`; the application is **ProjectFlow**.

![Thinking workspace with explicitly labelled fictional demo conversation](docs/screenshots/workbench.png)

## What works in V0.2

- Free conversation and 13 interactive thinking templates; six user-controlled thinking states; up to three follow-up directions after each AI answer, with rule-based fallback.
- Editable idea extraction with source-message references. Ideas, micro experiments and projects remain separate records.
- Project context, plan snapshots with change reasons, state-specific reflection prompts and in-app due reminders.
- Editable execution briefs, clipboard/Markdown export, explicit delegation states and manual/text/JSON result import. This app does **not** execute external agents.
- RSS/Atom parsing and deduplication, manual article entry, reading discussions and model-based article analysis. Finite feed discovery verifies the RSS/Atom links declared by websites you supply.
- Working local collaboration plaza: separate public snapshots, persisted comments, collaboration proposals and owner responses. Public-project AI receives only public snapshots/comments and the participant's explicit input.
- Four fictional demo identities and cross-domain projects in a separate resettable database. Core non-AI interactions work without an API key.

## Windows quick start

Requires Windows 10/11 and Miniconda/Conda. The app itself uses **Python 3.11 standard library only**; no Node, npm, Streamlit or paid service is required. Internet is needed initially to download Python through Conda.

1. Download/extract this source into a writable folder. Paths containing spaces and Chinese characters are supported.
2. Run `setup.bat`. It creates **only this project's `.conda-env`** and verifies the interpreter before dependency operations. If Conda cannot be found, run it from a Miniconda Prompt. An incomplete existing environment is left untouched and reported.
3. Run `start.bat`. Keep the console open. Your browser opens [the local app](http://127.0.0.1:43127).
4. Select **Demo Mode · 本地社区** in the top bar to explore without configuring a model.

To use Git instead of downloading a ZIP:

```powershell
git clone https://github.com/shipshipliucixin1/innovation-dance.git
cd innovation-dance
.\setup.bat
.\start.bat
```

The server always binds to `127.0.0.1`. To choose another local port, set `PROJECTFLOW_PORT` before starting. Stop with Ctrl+C. Setup never installs in base or another project environment, modifies PATH, runs `conda init`, changes GPU drivers or automatically rebuilds an environment.

## Configure an optional model

Open **设置 → AI 模型**. Enter your provider's OpenAI-compatible API root (typically ending in `/v1`), model name and optional API key. Apply configuration, then click **测试已应用的连接**. The test sends one actual small model request and may be billed by your provider. Redirecting model endpoints are rejected; enter the final URL.

An unchecked secure-storage option keeps the key only in server memory until the server stops. Checking it uses Windows Credential Manager through the native Windows API. Failure is reported; there is no plaintext fallback. Existing keys are never displayed. Non-Windows users can use `.env` or a session-only key.

Alternatively copy `.env.example` to `.env` and fill:

```dotenv
LLM_API_KEY=
LLM_BASE_URL=
LLM_MODEL=
```

Restart after editing `.env`. For startup non-secret settings, precedence is process environment → `.env` → saved GUI settings. A GUI change applies to the running process; restart reapplies environment settings. Key precedence is a GUI session key or saved Windows credential → process-environment/`.env` key. Clear the session/Windows credential to use an environment key instead. The clear-key button does **not** edit `.env`. Keyless local compatible models are supported. Base URLs, model names and timeout settings are stored locally; keys are never stored in SQLite or exported data.

Live chat, extraction, AI drafts, article analysis and public-project AI need a working model. Missing configuration and network errors are visible. Fixture dialogue is explicitly labelled; the app never silently substitutes demo answers for real model calls.

## Personal mode and local plaza

Personal mode starts empty. Add an article or open AI 工作台. Choose a thinking direction, fill one meaningful field, and continue discussing. Extract an idea, inspect/edit it, then save it. Generate an experiment or a project draft when ready. Every project edit creates a plan version. Record the evidence and reason for changes.

Use **交给 AI 执行** to create an editable brief. Without a model, choose **用项目字段组装**; this explicitly labelled operation assembles existing project fields. Copy/download the brief, submit it yourself to your external tool, then mark it delegated. Paste a result or import a `.txt`, `.md` or `.json` report (JSON fields: `summary`, `expected`, `evidence`, `paths`, `issues`, `unfinished`, `review`). File paths are text references; ProjectFlow does not read those files. AI review creates a linked private reflection conversation from saved reports.

To demonstrate collaboration, select Demo Mode and 林舟 (developer). Publish a project only after editing/checking the preview. Switch to 陈禾, open the public project, comment and propose a first collaboration step. Switch back to 林舟 to accept/decline. Refresh/restart: those records persist. The demo is a local identity simulation, **not account authentication**. Personal projects never automatically enter the demo plaza.

## Content discovery

Add a real RSS/Atom URL under Settings and synchronize manually. Or supply a blog homepage to **发现信息源**: the app reads its declared alternate RSS/Atom links and fetches each candidate to verify it. With no URL it checks up to five saved sources. Coverage is explicitly bounded; there is **no general search provider integration** in V0.2. Interests guide manual source selection and simple local article ordering. Article analysis is an explicit model operation, not a fabricated quality score. Respect publishers' terms and copyright; do not redistribute your article database.

## Data, migration and privacy

Everything is under the project folder unless a developer specifies `--data-root`:

| Location | Content |
| --- | --- |
| `data/personal.sqlite3` | Personal conversations, ideas, projects and local plaza |
| `data/demo.sqlite3` | Fictional identities/projects and actual local demo interactions |
| `data/model.json` | Base URL/model/timeout only |
| `.env` | Optional user-managed local secret configuration |
| Windows Credential Manager | Optional protected key, scoped to this checkout's absolute path |

Browser storage holds only the selected local mode/identity. It does not hold private records or keys. Stop the application before copying the database files for a full backup/restore. Settings can also export the current identity's records to inspectable JSON. V0.2 JSON export is an archive, **not an automatic restore format**. The old `ProjectFlow-local` v2 JSON export can be imported through Settings: additions only, one transaction, no old API settings/keys imported. Old localStorage and old application files are not modified. Do not import the same archive repeatedly unless you want duplicate copies.

Schema version 2 initializes new databases idempotently; upgrading an existing supported version makes a SQLite backup first. Unknown newer schemas are rejected. This is the first SQLite version; the old app had no SQLite database to migrate. Demo reset touches only the demo database.

Context sent to a provider includes the current conversation (last 20 messages), selected article text (up to 24,000 characters), linked project and interests; extraction/drafting uses selected records. Reflection includes project tasks and their manually supplied results. Public discussions use a separate context builder with only public whitelisted fields, up to 50 public comments, and that participant's public-discussion history/current input. It never fetches a private project or owner conversation. Public materials are text; no automatic private file fetching or agent tools exist.

The local server checks Host, Origin and a per-process CSRF token; static serving is allowlisted. External text is escaped. Feed requests reject local/private/reserved addresses and check redirect destinations. API credentials are not reflected from provider error bodies or logged. This is still a **single-user local application**: anyone with OS-level access or control of this localhost service can access local data/simulated identities. Do not expose it through a proxy, LAN binding or public tunnel. SQLite business data is not encrypted. This folder may itself be synced by your chosen cloud-sync software; its storage policy is outside ProjectFlow's control. `.gitignore` prevents accidental normal Git inclusion, not filesystem sync or malicious access.

## Development and tests

Windows, after setup:

```powershell
.\.conda-env\python.exe scripts\verify_env.py
.\.conda-env\python.exe -m unittest discover -s tests -v
.\.conda-env\python.exe -m projectflow.server --no-browser --data-root .qa
```

For macOS/Linux, create a project-local Conda environment with Python 3.11 and use `conda run -p ./.conda-env python -m projectflow.server`; Windows credential storage is unavailable there. CI uses isolated GitHub runners on Windows/Linux and only local model fixtures. No paid calls are used in tests. Browser UI checks and verification limits are documented in the development report.

Source layout: `projectflow/store.py` (SQLite), `thinking.py` (templates), `service.py` (business operations and ownership), `llm.py` (compatible client), `content.py` (feeds), `credentials.py` (native secure storage), `server.py` (HTTP), `static/` (retained design plus UI), `tests/` (core and loopback integration).

## Current limits and release boundary

No public multi-user authentication, real-time team sync, background notification service, automated coding agent, streaming output, general web search or learned recommendation model. Search discovery is finite, and providers/publishers may be unreachable. Long conversations/projects are intentionally small-scale; no pagination/search or optimistic editing conflict resolution yet. Context is selected, not an unlimited knowledge index. Model quality and real paid-provider integration must be checked with your chosen configuration. Internet-facing deployment requires a different security architecture.

Publishing the source does not start a hosted service or publish your local databases. MIT licence applies to ProjectFlow code and original fictional fixtures, not third-party content imported by users.

## Keep GitHub up to date

After changing code, double-click `update-github.bat`, review the listed changes and enter a short commit message. The shortcut fetches the remote, refuses to overwrite remote work, checks working files/index/history for known credential signatures and private/generated paths, commits changes, and performs an ordinary push to `origin/main`. It never force-pushes or rewrites existing commits. It uses only the project interpreter and existing Git authentication. A failed push leaves your local commit available to retry.

For manual commands and recovery, see [GitHub workflow](docs/GITHUB_WORKFLOW.md). The included scanner is a local heuristic, not an exhaustive secret-detection guarantee; review new documents and screenshots yourself. If it reports potential credentials, stop and investigate before any push.
