# GitHub Intelligence

**Understand Any Codebase. From Beginner to Expert.**

AI-Powered Repository Understanding Platform. Paste a GitHub repository URL and get a complete AI-powered explanation of its architecture, code, functions, dependencies, and execution flow — from beginner to advanced.

![GitHub Intelligence](https://img.shields.io/badge/Built%20with-Python%20%7C%20React%20%7C%20FastAPI%20%7C%20Tree--sitter-1a1b1e?style=for-the-badge&labelColor=4263eb&color=fff)

## Live Demo

Paste any public GitHub repository URL to:
1. Clone and analyze the full codebase
2. Parse source code with Tree-sitter AST analysis
3. Build a knowledge graph of all relationships
4. Detect architecture patterns and tech stack
5. Get Beginner, Intermediate, and Advanced explanations
6. Explore files, functions, and class relationships
7. Ask questions and get evidence-based answers
8. Generate comprehensive project documentation

## Features

| Feature | Description |
|---------|-------------|
| **Repository Analysis** | Clone, scan, and analyze any public GitHub repository |
| **AST Parsing** | Tree-sitter based parsing for JavaScript, TypeScript, Python, Java, C, C++ |
| **Code Graph** | Interactive visualization of file, function, class, and dependency relationships |
| **Three-Level Analysis** | Beginner, Intermediate, and Advanced explanations with progressive depth |
| **File Explorer** | Browse repository files with syntax-highlighted source and symbol panels |
| **AI Assistant** | Ask questions about the codebase and get evidence-based answers |
| **Report Generation** | One-click comprehensive project documentation in Markdown |
| **Architecture Detection** | Automatic identification of MVC, layered, REST API, and component-based patterns |
| **Symbol Extraction** | Functions, classes, methods, imports, exports, and call relationships |
| **Dependency Analysis** | Import resolution, cross-file calls, and circular dependency detection |

## Screenshots

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub Intelligence                                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Understand Any GitHub Repository                       │   │
│  │                                                         │   │
│  │  https://github.com/vercel/next.js                     │   │
│  │                                        [ Analyze ]      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐         │
│  │ Files    │ │Functions │ │ Classes  │ │Languages │         │
│  │   847    │ │  2,341   │ │   456    │ │    5     │         │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘         │
│                                                                 │
│  [Beginner] [Intermediate] [Advanced] [Graph] [Assistant]     │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- **Python 3.12+** ([download](https://www.python.org/downloads/))
- **Node.js 18+** ([download](https://nodejs.org/))
- **Git** ([download](https://git-scm.com/))

### Installation

```bash
# Clone the repository
git clone https://github.com/himaaanshuu/githubanalyzer.git
cd githubanalyzer

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows

# Install backend dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Running

**Option 1 — One command (both services):**
```bash
./start.sh
```

**Option 2 — Separate terminals:**
```bash
# Terminal 1 — Backend (port 8000)
cd backend
source ../venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (port 5173)
cd frontend
npm run dev
```

### Access

| Service | URL |
|---------|-----|
| **Frontend** | http://localhost:5173 |
| **Backend API** | http://localhost:8000 |
| **API Documentation** | http://localhost:8000/docs |

## How It Works

### Analysis Pipeline

```
User pastes GitHub URL
        ↓
   Validate URL
        ↓
   Clone Repository (shallow, secure)
        ↓
   Scan Files & Detect Languages
        ↓
   Tree-sitter AST Parsing
        ↓
   Extract Symbols (functions, classes, imports, exports, calls)
        ↓
   Build Knowledge Graph
        ↓
   Resolve Cross-File References
        ↓
   Detect Architecture & Tech Stack
        ↓
   Generate Three-Level Analysis
   ├── Beginner: What does this do?
   ├── Intermediate: How is it structured?
   └── Advanced: Code complexity, call graphs, security
        ↓
   Interactive Explorer
   ├── Browse Files
   ├── Visualize Code Graph
   ├── Ask Questions
   └── Generate Report
```

### Architecture

```
githubanalyzer/
├── backend/                          # Python FastAPI backend
│   ├── app/
│   │   ├── api/
│   │   │   ├── repositories.py      # Repo CRUD, analysis trigger
│   │   │   ├── analysis.py          # Beginner/Intermediate/Advanced
│   │   │   ├── graph.py             # Code graph endpoints
│   │   │   ├── questions.py         # AI Q&A
│   │   │   └── reports.py           # Report generation
│   │   ├── core/
│   │   │   ├── config.py            # App settings
│   │   │   ├── database.py          # SQLAlchemy async session
│   │   │   └── exceptions.py        # Custom errors
│   │   ├── models/
│   │   │   ├── database.py          # SQLAlchemy ORM models
│   │   │   └── schemas.py           # Pydantic API schemas
│   │   ├── analyzers/
│   │   │   ├── base.py              # Abstract Tree-sitter parser
│   │   │   ├── javascript.py        # JS/JSX parser
│   │   │   ├── typescript.py        # TS/TSX parser
│   │   │   └── python.py            # Python parser
│   │   ├── services/
│   │   │   └── analysis_service.py  # Full analysis pipeline
│   │   └── main.py                  # FastAPI app
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # React TypeScript frontend
│   ├── src/
│   │   ├── components/
│   │   │   └── Layout.tsx           # Sidebar navigation
│   │   ├── pages/
│   │   │   ├── HomePage.tsx         # Landing page with URL input
│   │   │   ├── RepositoryPage.tsx   # Dashboard with stats
│   │   │   ├── AnalysisPage.tsx     # 3-level analysis views
│   │   │   ├── FilesPage.tsx        # File tree + details
│   │   │   ├── GraphPage.tsx        # Interactive code graph
│   │   │   ├── AssistantPage.tsx    # AI Q&A chat
│   │   │   └── ReportPage.tsx       # Report generation
│   │   ├── lib/
│   │   │   └── api.ts               # Typed API client
│   │   ├── App.tsx                  # Router
│   │   └── main.tsx                 # Entry point
│   ├── package.json
│   ├── tailwind.config.js
│   └── Dockerfile
├── docker-compose.yml
├── start.sh
└── README.md
```

## API Reference

### Analyze a Repository
```bash
curl -X POST http://localhost:8000/api/repositories/analyze \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/pallets/markupsafe"}'
```

### Get Repository Details
```bash
curl http://localhost:8000/api/repositories/1
```

### Get Analysis at a Level
```bash
curl http://localhost:8000/api/repositories/1/analysis/beginner
curl http://localhost:8000/api/repositories/1/analysis/intermediate
curl http://localhost:8000/api/repositories/1/analysis/advanced
```

### Get Code Graph
```bash
curl http://localhost:8000/api/repositories/1/graph
curl http://localhost:8000/api/repositories/1/graph?node_type=function
```

### Ask a Question
```bash
curl -X POST http://localhost:8000/api/repositories/1/questions \
  -H "Content-Type: application/json" \
  -d '{"question": "How does authentication work?"}'
```

### Generate Report
```bash
curl -X POST http://localhost:8000/api/repositories/1/report
```

### Full API Reference
Visit http://localhost:8000/docs for interactive Swagger documentation.

## Supported Languages

| Language | Parser | Status |
|----------|--------|--------|
| JavaScript | Tree-sitter + JS grammar | Functions, classes, imports, exports, calls |
| TypeScript | Tree-sitter + TS grammar | All JS features + interfaces, type aliases |
| Python | Tree-sitter + Python grammar | Functions, classes, imports |
| Java | Tree-sitter (planned) | Coming soon |
| C | Tree-sitter (planned) | Coming soon |
| C++ | Tree-sitter (planned) | Coming soon |

## Docker

```bash
# Build and run all services
docker-compose up --build

# Or run in background
docker-compose up -d
```

Services:
- `backend` — FastAPI on port 8000
- `frontend` — React app served via nginx on port 5173

## Environment Variables

Create `backend/.env`:

```env
DATABASE_URL=sqlite+aiosqlite:///./github_intelligence.db
REDIS_URL=redis://localhost:6379
GITHUB_TOKEN=          # Optional: for private repos
LLM_API_KEY=           # Optional: for enhanced AI analysis
EMBEDDING_API_KEY=     # Optional: for vector search
```

## Development

```bash
# Backend with hot reload
cd backend && uvicorn app.main:app --reload

# Frontend with hot reload
cd frontend && npm run dev

# Type check frontend
cd frontend && npx tsc --noEmit

# Build frontend
cd frontend && npm run build
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python, FastAPI, SQLAlchemy, aiosqlite |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **Parsing** | Tree-sitter (JavaScript, TypeScript, Python) |
| **Database** | SQLite (async via aiosqlite) |
| **Visualization** | D3.js force-directed graph |
| **Icons** | Lucide React |

## License

MIT

---

**Built to help developers understand any codebase instantly.**
