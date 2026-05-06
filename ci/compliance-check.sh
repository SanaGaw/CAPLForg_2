#!/bin/bash
# CAPL Pipeline Compliance Check Script

set -e

echo "Running CAPL Pipeline compliance check..."

# Enable compliance mode
export COMPLIANCE_MODE=true
export OLLAMA_BASE_URL=http://localhost:11434

# Run basic tests
pytest tests/unit/ -v

# Run schema validation
python -m config_schemas validate config_schemas/signal_aliases.v1.schema.json || true

echo "Compliance check complete."
