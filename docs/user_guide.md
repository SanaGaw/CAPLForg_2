# CAPL Pipeline V2.2 User Guide

## Installation

```bash
# Clone repository
git clone <repository>
cd capl-pipeline-v2.2

# Install in development mode
pip install -e .

# Copy environment template
cp .env.example .env
# Edit .env with your configuration
```

## Basic Usage

### 1. Initialize Project

```bash
# From CANoe .cfg file
capl-pipeline init --cfg path/to/project.cfg

# Or create empty config
capl-pipeline init
```

### 2. Configure Signals

Edit `signal_aliases.yaml` to define signal name mappings:

```yaml
version: "1.0"
aliases:
  DoorLock_FL:
    target_path: "BCM_DoorLock_FrontLeft"
    bus_type: "CAN"
    source: "USER"
```

### 3. Generate Test Cases

```bash
# Generate from Excel test plan
capl-pipeline generate path/to/test_plan.xlsx

# Batch mode for parallel processing
capl-pipeline generate test_plan.xlsx --batch

# Dry run (preview without writing files)
capl-pipeline generate test_plan.xlsx --dry-run
```

### 4. Validate Generated CAPL

```bash
# Structural validation only
capl-pipeline validate output/test.can

# With CANoe compiler
capl-pipeline validate output/test.can --compiler
```

### 5. Compare Against Golden Files

```bash
capl-pipeline compare golden/ output/ --tolerance 0.95
```

## Web Interface

Start the web server:

```bash
capl-pipeline serve --port 8000
```

Open http://localhost:8000 in your browser.

### Signal Registry

View and manage all registered signals with their confidence scores.

### Gap Resolution Chat

Resolve configuration gaps through natural language conversation.

### Template Browser

Browse and select from available CAPL templates.

## Compliance Mode

Run in offline, audited mode:

```bash
capl-pipeline generate test_plan.xlsx --compliance
```

This enables:
- Local LLM processing only (Ollama)
- Full audit logging
- JSON-LD traceability export
- Network blocking

## Audit Log

View recent decisions:

```bash
capl-pipeline audit show --limit 50
```

Export to file:

```bash
capl-pipeline audit export --output audit_log.json
```

## Configuration

### Environment Variables

See `.env.example` for all available options.

Key variables:
- `LLM_PRIMARY_PROVIDER` - Primary LLM provider
- `LLM_PRIMARY_MODEL` - Primary model
- `COMPLIANCE_MODE` - Enable compliance mode
- `MAX_PARALLEL_TASKS` - Parallel processing limit
- `MAX_MEMORY_MB` - Memory limit for graceful abort

### API Configuration

Edit `api_config.yaml` for LLM provider settings:

```yaml
llm:
  preferred:
    provider: azure
    model: o3-mini
  fallback_chain:
    - provider: ollama
      model: qwen2.5-coder
```

## Troubleshooting

### "Signal not found" errors

Ensure signals are registered in the registry or `signal_aliases.yaml`.

### Low confidence scores

Run cross-validation to identify missing sources:
```bash
# View validation report in web UI
```

### LLM connection failures

Check provider credentials in `.env`:
- `AZURE_OPENAI_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `GOOGLE_CLOUD_PROJECT`

For offline mode, use Ollama:
```bash
ollama serve
```
