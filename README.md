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

## Architecture

```
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
