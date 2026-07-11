# Cerno AI — Backend (WIP)

> **Status:** Epic 1 complete (Foundation, Auth & Cross-Cutting Infra).
> This README is temporary — covers what exists today, not the full
> product. See `PRD.md`, `TDD.md`, `EPICS.md` for the complete design.

## What's built so far

- Typed, fail-fast `Settings` (config.py)
- SQLAlchemy + SQLite (WAL mode, StaticPool for in-memory tests), Alembic migrations
- Shared sentinel error families (`shared/errors.py`) + HTTP status mapping (`app/exception_handlers.py`)
- `APIResponse[T]` envelope for every route response
- Request-ID middleware + structured JSON logging
- Prompt-injection sanitizer + `@retry_transient` decorator
- In-memory IP rate limiter
- `ai/` package: `AIService` Protocol, graceful-degradation factory, OpenAI-compatible stub (methods raise `NotImplementedError` until Epic 2/3 wire in real prompts)
- **`auth/` — full vertical slice**: Google OAuth (CSRF-protected), stateless HMAC-signed cookie, no session table. Proof-point that the whole skeleton coheres end-to-end.

Everything else (`candidate_profile/`, `job_posting/`, `session/`,
`observation/`, `feedback/`) is an empty placeholder folder — Epic 2/3 work.

## Requirements

- Python 3.12+
- SQLite (bundled with Python — no separate install needed for v1)

## Setup

```bash
pip install -r requirements.txt   # or: pip install --break-system-packages -r requirements.txt

cp .env.example .env              # then fill in real values (see below)
```

### Required environment variables

| Variable | Notes |
|---|---|
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | From Google Cloud Console OAuth credentials |
| `COOKIE_SIGNING_SECRET` | Any long random string. **Must not be the dev default in production** — app refuses to boot otherwise |
| `LLM_API_KEY` | OpenAI-compatible provider key. App boots without it, but every `ai/` call degrades to unavailable |
| `DATABASE_URL` | Defaults to `sqlite:///./cerno.db` if unset |

All settings and their defaults live in `config.py` — that's the source of truth, not this table.

## Running

```bash
# Apply migrations (creates tables)
alembic upgrade head
```

> **Note:** no migration files exist yet — `alembic upgrade head` currently
> runs against an empty migration history. The `users` table is only
> created via `Base.metadata.create_all()` in test fixtures right now.
> Generate the first real migration before running against a persistent
> dev DB: `alembic revision --autogenerate -m "create users table"`
> (needs `auth.models` imported in `migrations/env.py` first — see the
> commented-out import there).

```bash
# Start the dev server
uvicorn app.main:app --reload
```

App boots at `http://localhost:8000`. Interactive API docs at `/docs`.

## Running tests

```bash
pytest
```

Tests live under `tests/`, mirroring the package structure (not colocated
with source — see note below). Repository tests hit a real in-memory
SQLite DB; service tests use fakes/mocks (no DB, no network); route
tests use FastAPI's `TestClient` against the fully-wired app.

```
tests/
  auth/
    test_repository.py   # real SQLite :memory:
    test_service.py      # fake repo, mocked Google OAuth
    test_routes.py        # TestClient, full app
  shared/security/
    test_sanitize.py
    test_retry.py
  app/
    test_exception_handlers.py
```

## Project structure

Domain-driven, not layer-driven — each domain folder is independently
readable without opening another domain's folder. Every domain follows
the same internal shape once built out:

```
<domain>/
  domain.py      -- pure Pydantic business objects, no ORM/HTTP
  models.py         -- SQLAlchemy ORM mapping only
  repository.py        -- data access; storage failures -> sentinel errors
  service.py               -- business logic/orchestration; only layer calling ai/ or external APIs
  errors.py                   -- domain-specific sentinel errors (subclass shared/errors.py)
  routes.py                      -- FastAPI handlers; parse request, call one service method, format response
```

```
app/            -- composition root: main.py, exception_handlers.py
api/v1/         -- router aggregation layer
auth/           -- ✅ built (Epic 1)
candidate_profile/, job_posting/, session/   -- Epic 2 (empty)
observation/, feedback/                       -- Epic 3 (empty)
ai/             -- AIService Protocol, factory, OpenAI-compatible stub
shared/
  db/           -- engine/session factory, declarative Base
  security/     -- sanitizer, retry decorator
  errors.py, schemas.py, middleware.py, logger.py, rate_limit.py
migrations/     -- Alembic
tests/          -- mirrors the package tree above
```

## Known gaps / not-yet-wired (tracked, not forgotten)

- `ai/` methods all raise `NotImplementedError` — real prompts land in Epic 2 (Interviewer, CV/GitHub structuring) and Epic 3 (Observer, Feedback Synthesizer)
- Retry decorator's `exceptions=` tuple in `ai/openai_compatible_service.py` uses placeholder exception types — needs real OpenAI SDK exception classes once actual API calls are wired in
- No account-deletion / data-retention path yet (see TDD's Privacy section)
- `Secure` cookie flag is `settings.is_production`-gated — **verify this is `True`** before any real deploy; dev/test intentionally relax it

## Docs

- `PRD.md` — product scope and philosophy (NVC-based feedback)
- `TDD.md` — full backend technical design
- `EPICS.md` — implementation plan, ticket-by-ticket
- `observer_prompt_draft.md`, `feedback_synthesizer_prompt_draft.md`, `interviewer_system_prompt.md` — LLM role prompts (not yet wired into `ai/`)
