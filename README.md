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

## Architecture

```
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