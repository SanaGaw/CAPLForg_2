# CAPL Pipeline V2.2 Architecture Specification

## Design Philosophy

`Deterministic-first, explainable-always. GUI-only for end-users. LLM bounded to config/chat. Zero probabilistic generation.`

## Core Principles

1. **Deterministic Output**: Same input always produces identical output
2. **Explainable**: Every decision is logged with full context
3. **GUI for End Users**: CLI only for CI/CD; web UI for interactive work
4. **LLM Bounded**: LLM only used for gap resolution and chat (not generation)
5. **Zero Hallucination**: No probabilistic CAPL generation

## System Components

### Parsers (`src/parsers/`)

Parsers extract structured data from CANoe project files:

| Parser | File Type | Output |
|--------|-----------|--------|
| CfgParser | .cfg | References (DBC, LDF, .can paths) |
| CanParser | .can | Signal↔EnvVar mappings, sysvar refs |
| DbcParser | .dbc | Messages, signals with properties |
| LdfParser | .ldf | LIN frames, signals |
| VsysvarParser | .vsysvar | System variable definitions |
| CinParser | .cin | Function signatures |
| CddParser | .cdd | DTC definitions |
| ExcelParser | .xlsx | Test cases, steps |
| StoSpecParser | .docx | Signal tables (IN/OUT/Cal/Proxi/DTC) |

### Core Modules (`src/core/`)

| Module | Purpose |
|--------|---------|
| SignalRegistry | SQLite-backed signal storage with 8-tier lookup |
| CrossValidator | Multi-source confidence scoring |
| ConfigBuilder | LLM-guided gap resolution orchestrator |
| PatternMatcher | Deterministic phrase library |
| PatternAnalyzer | Repeated sequence detection |
| AuditLogger | JSON-LD decision logging |
| CaplFingerprinter | Structural CAPL comparison |
| ConfigLoader | .env + YAML loading |

### CAPL Generation (`src/capl/`)

| Module | Purpose |
|--------|---------|
| TemplateEngine | Jinja2 sandboxed renderer |
| HelperManager | CIN signature validation |
| CaplGenerator | Main CAPL emission |
| TwoTierValidator | Structural + compiler validation |

### LLM Integration (`src/llm/`)

| Module | Purpose |
|--------|---------|
| LLMRouter | Multi-provider routing with circuit breaker |
| ChatResolver | Natural language gap resolution |
| PromptManager | Structured prompt templates |

### Web UI (`src/web/`)

- FastAPI backend with REST + WebSocket endpoints
- Vue 3 CDN SPA (no build step required)
- Signal registry viewer
- Gap resolution chat
- Template browser

### Compliance (`src/compliance/`)

| Module | Purpose |
|--------|---------|
| ComplianceManager | Network block, audit bundle generation |
| TraceabilityExporter | JSON-LD traceability matrices |
| OfflineResolver | Questionnaire-based fallback |

## Data Flow

```
Excel Test Plan
    ↓
ExcelParser → TestCase objects
    ↓
PatternMatcher → Action classification
    ↓
SignalRegistry.lookup() → Signal details
    ↓
TemplateEngine.render() → CAPL code
    ↓
TwoTierValidator → Validation
    ↓
Output .can files
```

## Signal Resolution (8-Tier Cascade)

1. Direct registration (highest priority)
2. Alias resolution
3. DBC database
4. LDF database
5. .vsysvar system variables
6. .can file mappings
7. STO specification
8. Excel test plan (lowest priority)

## Confidence Scoring

| Level | Range | Meaning |
|-------|-------|---------|
| Green | ≥0.8 | Confirmed by 2+ sources |
| Yellow | 0.5-0.8 | Confirmed by 1+ source |
| Orange | 0.2-0.5 | Conflicting information |
| Red | <0.2 | Unconfirmed |

## LLM Provider Chain

1. Azure OpenAI (primary)
2. AWS Bedrock (cross-provider fallback)
3. Google Vertex AI (validation)
4. Local Ollama (offline/compliance)

## Configuration Files

- `.env` - Environment variables
- `api_config.yaml` - LLM provider routing
- `signal_aliases.yaml` - Signal name mappings
- `helper_definitions.json` - CIN signatures
- `decisions.jsonl` - Audit log

## Development Guardrails

1. No Python `ast` for CAPL parsing
2. Pydantic v2 syntax only
3. Jinja2 SandboxedEnvironment required
4. Typer CLI standard pattern
5. Type hints mandatory
