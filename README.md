<<<<<<< HEAD
# CAPL Forge - Module 1

## CANoe Project Knowledge Extraction and Resolution System

**Module 1** extracts knowledge from CANoe projects (DBC, CDD, vsysvar, CAPL) and builds a SQLite knowledge base with semantic linking.

**Module 2** (not yet implemented) will generate CAPL from resolved test suites.

## Features

- **DBC Parsing**: Extract CAN/LIN messages and signals using cantools
- **Diagnostic Parsing**: CDD/CANdela data extraction
- **System Variables**: vsysvar file parsing
- **CAPL Analysis**: Handler detection, signal mapping extraction
- **Knowledge Base**: SQLite database with incremental updates
- **Query APIs**: Signal context, coverage reporting, statistics

## Module Scope

### What Module 1 Does
- Parse CANoe configuration files
- Extract all referenced engineering artifacts (DBC, CDD, vsysvar, CAPL)
- Build a SQLite knowledge base with semantic linking
- Provide query APIs for signal context and coverage analysis

### What Module 1 Does NOT Do
- Generate CAPL code (this is Module 2)
- AI/LLM integration (deferred until Module 2)
- Streamlit UI (future work)

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Scan a CANoe project

```bash
# Using --config option
python main.py scan-project --config /path/to/project.cfg --db output.db

# Or using environment variable
export CAPL_FORGE_CFG=/path/to/project.cfg
python main.py scan-project --db output.db
```

### Query a signal

```bash
python main.py query-signal FOO_SIGNAL_X
```

### Generate coverage report

```bash
python main.py coverage-report --db output.db
```

### Show knowledge base statistics

```bash
python main.py stats --db output.db
```

## Environment Variables

- `CAPL_FORGE_CFG`: Path to CANoe .cfg file (alternative to --config)

## Development

```bash
# Run tests
python -m pytest

# Run CLI help
python main.py --help
python main.py scan-project --help
python main.py coverage-report --help
```
=======
# CAPL Pipeline V2.2

CANoe CAPL Test Case Generation Pipeline

## Overview

CAPL Pipeline is an automated system for generating CAPL test cases from Excel test plans, with support for signal validation, cross-source verification, and LLM-guided configuration resolution.

## Quick Start

```bash
# Install dependencies
pip install -e .

# Initialize project
capl-pipeline init --cfg path/to/project.cfg

# Generate test cases
capl-pipeline generate path/to/test_plan.xlsx

# Start web interface
capl-pipeline serve
```

## Features

- **Parser Suite**: Parse DBC, LDF, vsysvar, CDD, Excel test plans, and STO specifications
- **Signal Registry**: SQLite-backed signal management with 8-tier cascade lookup
- **Cross-Validation**: Confidence scoring based on multi-source verification
- **Config Builder**: LLM-guided Q&A for resolving configuration gaps
- **Template Engine**: Jinja2 sandboxed CAPL generation
- **Two-Tier Validation**: Structural checks + CANoe compiler wrapper
- **Compliance Mode**: Audit logging with JSON-LD traceability
- **Web UI**: FastAPI + Vue 3 SPA for end-user interaction
>>>>>>> origin/master

## Architecture

```
<<<<<<< HEAD
CANoe Project (.cfg)
    |
    v
[CfgInspector]  -- extracts references, inventory
    |
    v
[Layer 1 Extractors]  -- DBC, CDD, vsysvar, CAPL
    |
    v
[Inspection Result JSON]
    |
    v
[build_knowledge_base]  -- SHA-256 deduplication, incremental updates
    |
    v
[SQLite Knowledge DB]  -- sources, messages, signals, sysvars, env_vars, etc.
```

## License

MIT
=======
capl-pipeline/
├── src/
│   ├── parsers/       # File format parsers
│   ├── core/          # Signal registry, validators
│   ├── capl/          # CAPL generation
│   ├── llm/           # LLM integration
│   ├── web/           # FastAPI + Vue SPA
│   ├── cli/           # Typer CLI
│   └── compliance/    # Audit & traceability
├── config_schemas/    # JSON schema definitions
├── templates/         # CAPL templates
└── tests/             # Unit & acceptance tests
```

## Documentation

See `docs/` directory for detailed documentation:
- `user_guide.md` - User guide
- `cli_reference.md` - CLI commands reference
- `architecture_v2.2.md` - Architecture specification
- `onboarding_checklist.md` - Getting started checklist

## License

MIT
>>>>>>> origin/master
