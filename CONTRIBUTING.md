# Contributing to ProjectFlow

Please keep the experience small, domain-neutral and honest about AI capabilities. Do not turn every thought into a task. Do not expose personal context through a shared model client.

## Development environment

Run `setup.bat` on Windows. Use only the project's `.conda-env` interpreter. Never install requirements in base, change global Conda configuration/PATH, or rebuild somebody else's environment. For Linux/macOS, create a local Conda prefix with Python 3.11. No runtime third-party packages are required.

```powershell
.\.conda-env\python.exe scripts\verify_env.py
.\.conda-env\python.exe -m unittest discover -s tests -v
.\.conda-env\python.exe -m projectflow.server --no-browser --data-root .qa
```

Tests create temporary databases under `tests/.tmp`, run disposable loopback HTTP fixtures, and use no paid API. Existing personal data is never a test fixture. `.qa` is a separate development data root. Real-provider tests are optional and must be labelled separately. Tests and CI cover Windows/Linux; GUI credential storage is Windows-only.

Before committing or pushing, run `.\.conda-env\python.exe scripts\check_secrets.py`. It checks eligible working files, the full index and reachable/reflog history (including commit messages and annotated tags), reports only rule/file/line locations, and never prints matching credential values. It also rejects generated/private paths even if somebody has force-added them. This is a heuristic check, so manually review new public material too. See [the update workflow](docs/GITHUB_WORKFLOW.md).

## Add a thinking template

Edit `projectflow/thinking.py` `_TEMPLATES`: choose a stable ID, a natural label and two or three specific questions. Do not fill in the user's reasoning. Add the ID to suitable state defaults; keep recommendations at three unique valid IDs. Run the input-validation and recommendation tests. The frontend renders these definitions automatically, so a separate form implementation is unnecessary.

## Content-source adapters

`content.py` normalizes URLs, restricts public feed requests, parses RSS/Atom and verifies homepage-declared feeds. New adapters must return actual title/link/content with stable deduplication keys, use bounded time/size limits, check redirects, and never fabricate URLs or articles. Use local fixtures in tests; respect publishers' access rules and licences. Expose a clear coverage label for search adapters. Do not add scraping credentials or a silently enabled search service.

## Data and AI boundaries

`store.py` owns persistence; each entity has its own indexed table and JSON payload. `service.py` validates ownership and allowed fields. Any new schema needs an explicit migration, backup, idempotence test and a newer-schema rejection. Do not modify a user's database to fit a test.

Private context uses `Service.private_context`; public context uses `Store.snapshot_context`. Public fields are an explicit allowlist, not a filtered dump of a private project. Tests must inject secret sentinels into author and participant private records and assert they never occur in public model requests. Proposal acceptance always belongs to the snapshot owner.

`llm.py` centralizes provider calls and errors. Structured task fields are in `SCHEMAS` and parsed before use. Do not log prompts, credentials or raw provider error bodies. Keys belong in session memory, Windows Credential Manager or a user-managed ignored `.env`. Never substitute a fixture for an unavailable live model.

## UI contributions

`static/app.js` uses escaped text, semantic controls and data-action dispatch; `style.css` extends retained `legacy-base.css`. Preserve free chat, optional templates, editable drafts, visible errors and source links. Every main action must persist or produce an inspectable result. Avoid inline scripts/styles and external font/CDN requirements. Check desktop and narrow layouts, keyboard focus, forms, reload persistence and no-model behavior in a browser.

## Pull requests and publishing

Explain the observable behavior, validation performed and remaining limits. Include only source, original fictional fixtures and documentation. Exclude `.env`, databases, environments, exports and personal content. Run the offline suite; use the included CI. Do not publish a server, change repository visibility or push private data without explicit owner authorization. Contributions use the repository's MIT licence; imported third-party content retains its own rights.
