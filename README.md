# BankBot

A local-first application that parses South African bank statement PDFs, auto-classifies
transactions using a local LLM, and lets you explore your spending through a
modern web UI or CLI chat interface. All data stays on your machine.

## Supported Banks

- [FNB](https://www.fnb.co.za/) (First National Bank) - PDF parsing
- [Investec](https://www.investec.com/) Private Bank - PDF parsing + [Programmable Banking API](https://developer.investec.com/)

Want to add support for another bank? See [Adding Support for New Banks](
#adding-support-for-new-banks).

> [!WARNING]
> This application processes sensitive financial data. **Run locally only** - do
> not deploy to cloud services or expose to the internet. Your bank statements
> contain personal information that should never leave your machine.

> [!IMPORTANT]
> **DISCLAIMER**
>
> BankBot is an independent, open-source project. It is **not affiliated with,
> endorsed by, or sponsored by** FNB, Investec, or any other financial
> institution. All bank names, logos, and trademarks are the property of their
> respective owners and are referenced only for interoperability.
>
> Transaction classifications, totals, and chat responses are produced by a
> local language model and **may be inaccurate, incomplete, or out of date**.
> Nothing in this tool constitutes financial, tax, accounting, or legal advice.
> Always verify figures against your official bank statements before making
> any financial decision.
>
> This software is provided "as is", without warranty of any kind. You assume
> all risk associated with its use, including but not limited to data loss,
> misclassification, and reliance on any generated output.

## Features

- **PDF Parsing**: Extract transactions from FNB and Investec bank statement PDFs
- **Investec API**: Fetch transactions directly from the Investec Programmable Banking API
- **Auto-Classification**: Uses local LLM to categorize transactions (doctor, groceries, utilities, etc.)
- **Chat Interface**: Ask natural language questions about your spending
- **Cashflow Forecasting**: Detects recurring payments and income, projects daily
  balances up to 400 days ahead, flags overdraw risks before they happen, and
  answers "Can I afford this?" with a simulated yes/no verdict
- **REST + WebSocket API**: Integrate with frontend applications
- **Web Frontend**: Svelte-based dashboard with chat, transactions, analytics, and forecast
- **Analytics**: Pie charts showing spending breakdown per statement
- **Budget Tracking**: Set monthly budgets per category and track actual vs budgeted spending
- **File Watcher**: Automatically imports new statements when added
- **Extensible**: Easy to add support for new banks

## Tech Stack

- **Backend**: Python 3.11+ (FastAPI, SQLite)
- **Frontend**: Svelte 5, Tailwind CSS
- **AI**: MLX (Apple Silicon) or any OpenAI-compatible API (e.g., [LM Studio](https://lmstudio.ai/))

## Requirements

- Python 3.11+
- Node.js 18+
- **Apple Silicon**: No additional requirements (uses MLX for local inference)
- **Other platforms**: [LM Studio](https://lmstudio.ai/) or any OpenAI-compatible LLM server

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd BankBot

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# Install with MLX support (Apple Silicon only - recommended)
pip install -e ".[mlx]"

# Install with test dependencies (pytest, coverage)
pip install -e ".[test]"

# Install with both MLX and test dependencies
pip install -e ".[mlx,test]"
```

## Setup

### Configuration

Copy the example config to create your local `config.yaml`:

```bash
cp config.yaml.example config.yaml
```

`config.yaml` is gitignored so your credentials stay out of the repo. Edit it to
set your bank, LLM backend, and (if using Investec API) your client ID, client
secret, and API key. Investec credentials can also be supplied via the
`INVESTEC_CLIENT_ID`, `INVESTEC_CLIENT_SECRET`, and `INVESTEC_API_KEY`
environment variables.

### Option A: MLX Backend (Apple Silicon - Recommended)

No external server required. The model runs directly on your Mac using MLX.

1. **Install with MLX support**:
   ```bash
   pip install -e ".[mlx]"
   ```

2. **Configure** (optional - edit `config.yaml`):
   ```yaml
   bank: fnb
   llm:
     backend: mlx                                  # Use MLX for local inference
     model: mlx-community/GLM-4.7-Flash-4bit      # Default model (auto-downloaded)
   ```

3. **Add statements**: Place PDF bank statements in the `statements/` directory

The model will be downloaded automatically on first run (~2.5GB).

### Option B: OpenAI-Compatible API (LM Studio, Ollama, etc.)

1. **Install and start LM Studio**:
   ```bash
   # Install LM Studio (macOS)
   brew install --cask lm-studio
   open -a "LM Studio"

   # Set up CLI tools (first time only)
   ~/.lmstudio/bin/lms bootstrap
   source ~/.zshrc
   ```

2. **Get a model**: `lms get` lowercases repo names, so mixed-case HuggingFace
   repos like `mlx-community/Qwen3-8B-4bit` fail with "artifact does not exist
   or you do not have permission". Use the full URL to preserve case, or import
   from an existing HuggingFace cache (no re-download):

   ```bash
   # Via full URL (preserves case):
   lms get https://huggingface.co/mlx-community/Qwen3-8B-4bit --mlx -y

   # Or import from a local HuggingFace cache (no download):
   SNAP=$(ls -d ~/.cache/huggingface/hub/models--mlx-community--Qwen3-8B-4bit/snapshots/*/ | head -1)
   mkdir -p ~/.lmstudio/models/mlx-community/Qwen3-8B-4bit
   cp "$SNAP"* ~/.lmstudio/models/mlx-community/Qwen3-8B-4bit/
   ```

3. **Load the model and start the server**:
   ```bash
   lms load qwen3-8b
   lms server start
   ```

   The API model id is `qwen3-8b` (confirm with `curl localhost:1234/v1/models`).
   On a 16 GB Mac prefer the 8B: the 14B spills into swap. On the Developer tab
   of the LM Studio app, Start Server on port 1234.

4. **Configure** (`config.yaml`):
   ```yaml
   bank: fnb
   llm:
     backend: openai              # Use OpenAI-compatible API
     host: localhost
     port: 1234                   # LM Studio default port
     model: qwen3-8b              # Model id served by LM Studio
   ```

5. **Add statements**: Place PDF bank statements in the `statements/` directory

## Usage

```bash
# Activate virtual environment
source .venv/bin/activate

# Import all PDF statements
bankbot import

# Watch for new statements (auto-import)
bankbot watch

# Start interactive chat
bankbot chat

# List recent transactions
bankbot list
bankbot list -n 50    # Show 50 transactions

# Search transactions
bankbot search "doctor"
bankbot search "woolworths"

# View spending by category
bankbot categories

# Database statistics
bankbot stats

# List available bank parsers
bankbot parsers

# Rename PDFs to standardized format: {number}_{month}_{year}.pdf
# This ensures statements are imported in chronological order
bankbot rename

# Re-import a specific statement (useful after updating classification rules)
bankbot reimport statements/288_Nov_2025.pdf

# Re-import all statements
bankbot reimport --all

# Import Investec PDF statements
bankbot import --bank investec --path ~/path/to/investec/statements/

# Fetch transactions from Investec API
bankbot fetch-investec --from-date 2026-01-01 --to-date 2026-01-31
bankbot fetch-investec --list-accounts
bankbot fetch-investec --all              # Fetch all accounts (current month)

# Fetch a multi-month range for all accounts (API serves ~180 days of history).
# Existing transactions are skipped via per-transaction dedup, so re-running is safe.
bankbot fetch-investec --all --from-date 2025-10-01 --to-date 2026-08-04

# Export budgets to JSON or YAML
bankbot export-budget budgets.json
bankbot export-budget budgets.yaml

# Import budgets from file (clears existing budgets first)
bankbot import-budget budgets.json

# Forecast future balances and cashflow risks (31 days by default)
bankbot forecast
bankbot forecast --days 60 --buffer 1000   # warn below a R1,000 buffer
bankbot forecast --no-burn                 # committed recurring flows only
bankbot forecast --account all             # consolidate every account

# List detected recurring payments and income
bankbot recurring

# Check whether an expense is affordable today or on a future date
bankbot afford 500
bankbot afford 5000 --in-days 14

# Start API server (REST + WebSocket)
bankbot serve
bankbot serve --port 3000
```

> [!WARNING]
> The API has **no authentication**. `bankbot serve` binds to `127.0.0.1`
> (your machine only) by design. Do **not** use `--host 0.0.0.0`: that
> exposes your full financial data, chat, and budget write endpoints to
> everyone on your network.

## Re-importing Statements

If you update classification rules in `config.yaml`, you'll need to clear the database and re-import to apply the new rules:

```bash
# Delete the database and re-import all statements
rm ./data/statements.db && bankbot import
```

## Chat Examples

Once you've imported statements, start a chat session:

```
$ bankbot chat

You: When did I last pay the doctor?
Assistant: Your last payment to a doctor was on 2024-01-15 for R850.00...

You: How much did I spend on groceries last month?
Assistant: Last month you spent R4,523.50 on groceries across 12 transactions...

You: Show my largest expenses
Assistant: Your largest expenses were...

You: Can I afford R500 on Friday?
Assistant: Yes, you can afford R500.00. Your lowest balance afterwards
would still be R2,318.40 around 4 September 2026.

You: What are my recurring payments?
Assistant: You have 9 recurring payments totalling about R12,450.00 per month...
```

## Adding Support for New Banks

1. Create a new file in `src/parsers/` (e.g., `standardbank.py`)
2. Implement a parser class that inherits from `BaseBankParser`:

```python
from . import register_parser
from .base import BaseBankParser, StatementData

@register_parser
class StandardBankParser(BaseBankParser):
    @classmethod
    def bank_name(cls) -> str:
        return "standardbank"

    def parse(self, pdf_path) -> StatementData:
        # Implement PDF parsing logic
        ...
```

3. Update `config.yaml`:
   ```yaml
   bank: standardbank
   ```

## Investec API Setup

To fetch transactions directly from the Investec Programmable Banking API:

1. Enrol for [Programmable Banking](https://developer.investec.com/) on the Investec website
2. Configure credentials in `config.yaml` or via environment variables:

```yaml
investec:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  api_key: "your_api_key"
```

Or set environment variables (these take precedence over config):
```bash
export INVESTEC_CLIENT_ID="your_client_id"
export INVESTEC_CLIENT_SECRET="your_client_secret"
export INVESTEC_API_KEY="your_api_key"
```

## Configuration

Edit `config.yaml` to customize:

```yaml
# Bank parser to use (fnb or investec)
bank: fnb

# LLM settings
llm:
  # Backend: "mlx" (Apple Silicon) or "openai" (LM Studio, Ollama, etc.)
  backend: mlx

  # For MLX backend (Apple Silicon):
  model: mlx-community/GLM-4.7-Flash-4bit    # HuggingFace model ID

  # For OpenAI backend (uncomment to use):
  # backend: openai
  # host: localhost
  # port: 1234
  # model: qwen3-8b

# File paths
paths:
  statements_dir: ./statements
  database: ./data/statements.db

# Transaction categories (customize as needed)
categories:
  - doctor
  - optician
  - groceries
  - garden_service
  - dog_parlour
  - domestic_worker
  - education
  - fuel
  - utilities
  - insurance
  - entertainment
  - transfer
  - salary
  - other

# Classification rules (override LLM for specific patterns)
classification_rules:
  "Woolworths": groceries
  "Shell": fuel
  "Engen": fuel
  "School Fees": education
```

## API

Start the API server with `bankbot serve`. Interactive docs available at `http://localhost:8000/docs`.

### REST Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/stats` | Database statistics |
| GET | `/api/v1/categories` | List all categories |
| GET | `/api/v1/categories/summary` | Spending by category |
| GET | `/api/v1/transactions` | Paginated list (`?limit=20&offset=0`) |
| GET | `/api/v1/transactions/search?q=term` | Search transactions |
| GET | `/api/v1/transactions/category/{cat}` | Filter by category |
| GET | `/api/v1/transactions/type/{type}` | Filter by debit/credit |
| GET | `/api/v1/transactions/date-range?start=&end=` | Date range filter |
| GET | `/api/v1/statements` | List all statements |
| GET | `/api/v1/analytics/latest` | Analytics for latest statement |
| GET | `/api/v1/analytics/statement/{num}` | Analytics for specific statement |
| GET | `/api/v1/budgets` | List all budgets |
| POST | `/api/v1/budgets` | Create/update budget |
| DELETE | `/api/v1/budgets/{category}` | Delete a budget |
| GET | `/api/v1/budgets/summary` | Budget vs actual comparison |
| GET | `/api/v1/forecast/recurring` | Detected recurring payments (`?min_count=3&account=`) |
| GET | `/api/v1/forecast/balance` | Projected daily balances (`?days=31&include_burn=true&buffer=0&account=`) |
| GET | `/api/v1/forecast/afford` | Affordability check (`?amount=500&days_ahead=0&account=`) |

### WebSocket Chat

Connect to `ws://localhost:8000/ws/chat` for real-time chat.

**Send:**
```json
{"type": "chat", "payload": {"message": "How much did I spend on groceries?"}}
```

**Receive:**
```json
{
  "type": "chat_response",
  "payload": {
    "message": "You spent R2,450 on groceries...",
    "transactions": [...],
    "timestamp": "2025-01-07T10:30:00"
  }
}
```

Each WebSocket connection maintains its own conversation history for follow-up questions.

## Web Frontend

A Svelte-based web interface is included in the `frontend/` directory.

### Frontend Setup

```bash
# Install frontend dependencies
cd frontend
npm install

# Start development server (runs on port 5173)
npm run dev
```

### Running Full Stack

You need two terminals:

```bash
# Terminal 1: Start the backend API
source .venv/bin/activate
bankbot serve

# Terminal 2: Start the frontend
cd frontend
npm run dev
```

Then open http://localhost:5173 in your browser.

### Frontend Features

- **Chat**: Real-time WebSocket chat with transaction context
- **Dashboard**: Stats overview and spending by category chart
- **Forecast**: Projected balance chart, cashflow risk alerts, recurring
  payments table, and a "Can I Afford It?" simulator
- **Analytics**: Pie charts showing spending breakdown per statement with statement selector
- **Budget**: Set budgets per category, track spending with progress bars (color-coded: green/yellow/red)
- **Transactions**: Searchable, filterable transaction list with pagination

### Building for Production

```bash
cd frontend
npm run build
```

The built files will be in `frontend/dist/`.

## Docker

Run the backend and the nginx-served frontend with docker compose:

```bash
docker compose up -d --build
```

Open http://localhost:8080. The API is also exposed on http://localhost:8000
for debugging. `./data` and `./statements` are mounted read-write, so your
existing database and PDFs are used as-is; import statements with:

```bash
docker compose exec bankbot bankbot import
```

### LLM configuration

The container cannot use the MLX backend (Apple Silicon only). It defaults to
the OpenAI-compatible backend and connects to an LLM server on the host through
`host.docker.internal`:

```yaml
# docker-compose.yml
environment:
  BANKBOT_LLM_HOST: host.docker.internal # the host machine, from inside the container
  BANKBOT_LLM_PORT: "1234"               # LM Studio default; 11434 for Ollama
  BANKBOT_LLM_MODEL: "qwen3-8b"          # must match what /v1/models returns
```

Prerequisite on the host: an OpenAI-compatible LLM server listening on the port
above, serving the model id set in `BANKBOT_LLM_MODEL` (LM Studio: Developer tab
-> Start Server, `lms load qwen3-8b`). See
[Option B: OpenAI-Compatible API](#option-b-openai-compatible-api-lm-studio-ollama-etc).

`BANKBOT_*` environment variables override `config.yaml`, so the image runs with
its baked example config. Available: `BANKBOT_LLM_BACKEND`, `BANKBOT_LLM_HOST`,
`BANKBOT_LLM_PORT`, `BANKBOT_LLM_MODEL`, `BANKBOT_DB`, `BANKBOT_STATEMENTS_DIR`,
and `BANKBOT_ALLOWED_ORIGINS` (comma-separated browser origins, default allows
the vite dev server and the nginx proxy).

### Images

- `bankbot` backend image: `ghcr.io/ashleykleynhans/bankbot` (published
  automatically by the Docker workflow on pushes to `main` and `v*` tags)
- `frontend` service: built locally from `frontend/Dockerfile` (not published)

Build and push the backend image manually (multi-arch amd64 + arm64):

```bash
docker buildx bake push
```

## Project Structure

```
BankBot/
├── statements/           # Place PDF files here
├── data/
│   └── statements.db    # SQLite database (includes budgets table)
├── src/
│   ├── main.py          # CLI entry point
│   ├── database.py      # Database operations
│   ├── forecast.py      # Cashflow forecast engine (recurring, projection, affordability)
│   ├── classifier.py    # LLM classifier
│   ├── chat.py          # Chat interface
│   ├── watcher.py       # File watcher
│   ├── config.py        # Config loader
│   ├── llm_backend.py   # LLM backend abstraction (MLX/OpenAI)
│   ├── api/             # REST + WebSocket API
│   │   ├── app.py       # FastAPI application
│   │   ├── models.py    # Pydantic schemas
│   │   ├── session.py   # WebSocket session management
│   │   └── routers/
│   │       ├── stats.py       # Stats and categories
│   │       ├── transactions.py # Transaction queries
│   │       ├── analytics.py   # Analytics endpoints
│   │       ├── budgets.py     # Budget CRUD
│   │       ├── forecast.py    # Forecast endpoints
│   │       └── chat.py        # WebSocket chat
│   ├── investec_api.py  # Investec Programmable Banking API client
│   └── parsers/
│       ├── base.py      # Base parser class
│       ├── fnb.py       # FNB parser
│       ├── investec.py  # Investec parser
│       └── __init__.py  # Parser registry
├── frontend/             # Svelte web frontend
│   ├── src/
│   │   ├── App.svelte   # Main app layout
│   │   ├── lib/         # API client, WebSocket, stores
│   │   └── components/
│   │       ├── Chat.svelte        # Chat interface
│   │       ├── Dashboard.svelte   # Stats overview
│   │       ├── Forecast.svelte    # Cashflow forecast page
│   │       ├── Analytics.svelte   # Pie chart analytics
│   │       ├── Budget.svelte      # Budget management
│   │       ├── Transactions.svelte # Transaction list
│   │       ├── PieChart.svelte    # Reusable pie chart
│   │       └── CategoryChart.svelte # Bar chart
│   ├── package.json
│   └── vite.config.js
├── tests/                # Test suite
├── config.yaml
├── Dockerfile            # Backend image (uv builder + python runtime)
├── docker-bake.hcl       # Multi-arch GHCR build targets
├── docker-compose.yml    # Backend + frontend/nginx stack
└── pyproject.toml
```

## Privacy Note

Your bank statements contain sensitive financial data. This application:
- Processes everything locally (no cloud services)
- Uses a local LLM (MLX on Apple Silicon, or any OpenAI-compatible API)
- Stores data in a local SQLite database
- Never sends data to external servers

The `statements/` and `data/` directories are gitignored by default.

## License

Apache License 2.0
