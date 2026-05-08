# CAPL Pipeline CLI Reference

## Commands

### `capl-pipeline version`

Show version information.

```bash
capl-pipeline version
```

### `capl-pipeline init`

Initialize a new project.

```bash
capl-pipeline init [OPTIONS]

Options:
  -o, --output PATH    Output directory [default: .]
  --cfg FILE          CANoe .cfg file to scaffold from
```

### `capl-pipeline generate`

Generate CAPL test cases from Excel test plan.

```bash
capl-pipeline generate EXCEL_FILE [OPTIONS]

Options:
  -o, --output PATH    Output directory [default: output]
  --db PATH           Signal registry database path
  --batch             Use batch processing
  --dry-run           Preview without writing files
  --compliance       Run in compliance mode
```

### `capl-pipeline validate`

Validate a CAPL file.

```bash
capl-pipeline validate CAPL_FILE [OPTIONS]

Options:
  --compiler          Run CANoe compiler validation
```

### `capl-pipeline compare`

Compare generated files against golden references.

```bash
capl-pipeline compare GOLDEN_DIR GENERATED_DIR [OPTIONS]

Options:
  -t, --tolerance FLOAT  Similarity tolerance (0.0-1.0) [default: 0.95]
```

### `capl-pipeline audit`

View or export audit logs.

```bash
capl-pipeline audit ACTION [OPTIONS]

Actions:
  show    Show recent audit entries
  export  Export to file

Options:
  -o, --output PATH    Output file for export
  -n, --limit INT     Number of entries [default: 100]
```

### `capl-pipeline serve`

Start the web server.

```bash
capl-pipeline serve [OPTIONS]

Options:
  --host TEXT         Host to bind [default: 0.0.0.0]
  -p, --port INT      Port to bind [default: 8000]
  --reload            Enable auto-reload
```

### `capl-pipeline config-validate`

Validate a configuration file.

```bash
capl-pipeline config-validate CONFIG_FILE
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Validation failed |
| 3 | File not found |
