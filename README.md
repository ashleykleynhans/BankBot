# BankBot

A local-first application that parses South African bank statement PDFs, auto-classifies
transactions using a local LLM, and lets you explore your spending through a
modern web UI or CLI chat interface. All data stays on your machine.

## Supported Banks

- [FNB](https://www.fnb.co.za/) (First National Bank)

Want to add support for another bank? See [Adding Support for New Banks](
#adding-support-for-new-banks).

> [!WARNING]
> This application processes sensitive financial data. **Run locally only** - do
> not deploy to cloud services or expose to the internet. Your bank statements
> contain personal information that should never leave your machine.

## Features

- **PDF Parsing**: Extract transactions from bank statement PDFs
- **Auto-Classification**: Uses local LLM to categorize transactions (doctor, groceries, utilities, etc.)
- **Chat Interface**: Ask natural language questions about your spending
- **REST + WebSocket API**: Integrate with frontend applications
- **Web Frontend**: Svelte-based dashboard with chat, transactions, and analytics
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

   # Download and start a model
   lms get openai/gpt-oss-20b
   lms load openai/gpt-oss-20b
   lms server start
   ```

2. **Configure** (`config.yaml`):
   ```yaml
   bank: fnb
   llm:
     backend: openai              # Use OpenAI-compatible API
     host: localhost
     port: 1234                   # LM Studio default port
     model: openai/gpt-oss-20b    # Model for classification
   ```

3. **Add statements**: Place PDF bank statements in the `statements/` directory

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

# Export budgets to JSON or YAML
bankbot export-budget budgets.json
bankbot export-budget budgets.yaml

# Import budgets from file (clears existing budgets first)
bankbot import-budget budgets.json

# Start API server (REST + WebSocket)
bankbot serve
bankbot serve --host 0.0.0.0 --port 3000
```

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

## Configuration

Edit `config.yaml` to customize:

```yaml
# Bank parser to use
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
  # model: openai/gpt-oss-20b

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
- **Analytics**: Pie charts showing spending breakdown per statement with statement selector
- **Budget**: Set budgets per category, track spending with progress bars (color-coded: green/yellow/red)
- **Transactions**: Searchable, filterable transaction list with pagination

### Building for Production

```bash
cd frontend
npm run build
```

The built files will be in `frontend/dist/`.

## Project Structure

```
BankBot/
├── statements/           # Place PDF files here
├── data/
│   └── statements.db    # SQLite database (includes budgets table)
├── src/
│   ├── main.py          # CLI entry point
│   ├── database.py      # Database operations
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
│   │       └── chat.py        # WebSocket chat
│   └── parsers/
│       ├── base.py      # Base parser class
│       ├── fnb.py       # FNB parser
│       └── __init__.py  # Parser registry
├── frontend/             # Svelte web frontend
│   ├── src/
│   │   ├── App.svelte   # Main app layout
│   │   ├── lib/         # API client, WebSocket, stores
│   │   └── components/
│   │       ├── Chat.svelte        # Chat interface
│   │       ├── Dashboard.svelte   # Stats overview
│   │       ├── Analytics.svelte   # Pie chart analytics
│   │       ├── Budget.svelte      # Budget management
│   │       ├── Transactions.svelte # Transaction list
│   │       ├── PieChart.svelte    # Reusable pie chart
│   │       └── CategoryChart.svelte # Bar chart
│   ├── package.json
│   └── vite.config.js
├── tests/                # Test suite
├── config.yaml
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

GPLv3
