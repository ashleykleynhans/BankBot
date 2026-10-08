# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-10-08

### Added

- `bankbot reclassify` command to re-apply classification rules to existing
  transactions in place, with `--llm` to re-run the LLM on rule misses and
  `--dry-run` to preview changes without writing

## [0.2.0] - 2026-09-26

### Added

- Transaction search by amount in the web UI, API, and CLI (e.g. `3,341`
  matches R3,341.00, tolerating currency symbols, signs, and thousands
  separators)
- Cashflow forecasting: recurring payment detection from transaction history
  (weekly, fortnightly, and monthly cadences with confidence scoring,
  staleness detection for stopped subscriptions, and a 12-month recency
  window so long-dead payments never appear in forecasts)
- Daily balance projection over a configurable horizon, combining committed
  recurring flows with an average daily non-recurring burn rate
- Cashflow risk alerts: critical warnings when the projected balance drops
  below zero, optional safety-buffer warnings, and upcoming debits for the
  next seven days
- Affordability checks: simulate a purchase today or on a future date and get
  a yes/no verdict with the resulting lowest balance, headroom, and debits
  scheduled before the purchase
- Account-scoped forecasting across multi-account databases, defaulting to the
  most recently active account, with `--account all` consolidation
- New CLI commands: `forecast`, `recurring`, and `afford`
- New REST endpoints: `/api/v1/forecast/recurring`, `/api/v1/forecast/balance`,
  and `/api/v1/forecast/afford`
- Deterministic chat answers for "can I afford", recurring payment, and
  forecast questions (date arithmetic bypasses the LLM)
- Forecast page in the web frontend with a projected-balance chart, risk
  alerts, a recurring payments table, and a "Can I Afford It?" simulator

### Changed

- Bumped Python and frontend dependencies to their latest versions

## [0.1.0] - 2026-08-18

### Added

- FNB and Investec PDF statement parsing, including OCR for scanned FNB statements
- Investec Programmable Banking API integration: OAuth2 client, account listing,
  transaction fetching with per-transaction deduplication, and a `fetch-investec`
  CLI command
- Local LLM transaction classification into configurable categories with
  rule-based overrides
- Natural language chat interface (CLI and web) with conversation history,
  follow-up queries, brand-typo tolerance and correction, and budget-aware answers
- Svelte web frontend: chat, dashboard, analytics charts, budget management,
  and paginated transactions
- REST and WebSocket API with interactive docs
- Budget tracking: set, update, and remove budgets via chat or the web UI, plus
  budget import/export
- File watcher that auto-imports new statements
- MLX (Apple Silicon) and OpenAI-compatible (LM Studio, Ollama) LLM backends,
  selectable per environment
- Docker packaging: backend image, nginx-served frontend, docker compose stack,
  and multi-arch (amd64/arm64) publishing to GHCR
- Deterministic responses for price-change and budget queries (no LLM required)
- CSV transaction export and OCR debugging tool

### Fixed

- Phantom transactions from FNB bank charges columns
- Statement parsing issues, including dates without spaces and OCR artifacts
- Chat history handling on errors and cancelled requests
- Brand-typo detection leaking misspellings into answers and history
- Budget context hallucinations and incorrect math in responses
- Role alternation and follow-up detection in multi-turn chat
- Missing tables now return a clear import instruction instead of a raw error
- LLM connection failures surface the configured endpoint for diagnosis

### Security

- API hardened against cross-origin access and SQL injection
- Statements, data, and local config excluded from the Docker image
- WebSocket origin allowlist, configurable via `BANKBOT_ALLOWED_ORIGINS`
