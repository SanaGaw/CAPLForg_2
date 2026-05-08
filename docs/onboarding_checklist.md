# CAPL Pipeline V2.2 Onboarding Checklist

## Prerequisites

- [ ] Python 3.10+ installed
- [ ] Git installed
- [ ] Access to CANoe project files (DBC, LDF, .cfg)
- [ ] Excel test plans (Capgemini format)

## Step 1: Installation

- [ ] Clone repository
- [ ] Create virtual environment
- [ ] Install dependencies: `pip install -e .`
- [ ] Install dev dependencies: `pip install -e ".[dev]"`
- [ ] Run tests: `pytest tests/unit/ -v`

## Step 2: Configuration

- [ ] Copy `.env.example` to `.env`
- [ ] Configure LLM provider credentials
- [ ] Create `api_config.yaml` for provider routing
- [ ] Verify configuration: `capl-pipeline version`

## Step 3: Project Setup

- [ ] Initialize with CANoe .cfg: `capl-pipeline init --cfg project.cfg`
- [ ] Review generated `scaffold_config.yaml`
- [ ] Verify signal parsing: Check DBC/LDF extraction
- [ ] Register custom aliases in `signal_aliases.yaml`

## Step 4: Test Generation

- [ ] Prepare Excel test plan
- [ ] Run generation: `capl-pipeline generate test_plan.xlsx`
- [ ] Review output in `output/` directory
- [ ] Validate CAPL: `capl-pipeline validate output/test.can`
- [ ] Compare with golden files: `capl-pipeline compare golden/ output/`

## Step 5: Web Interface (Optional)

- [ ] Start server: `capl-pipeline serve`
- [ ] Open http://localhost:8000
- [ ] Browse signal registry
- [ ] Test gap resolution chat
- [ ] Verify templates display

## Step 6: Compliance Mode (Optional)

- [ ] Enable `COMPLIANCE_MODE=true` in `.env`
- [ ] Run with offline mode: `capl-pipeline generate test_plan.xlsx --compliance`
- [ ] Verify audit log: `capl-pipeline audit show`
- [ ] Export compliance bundle
- [ ] Verify traceability matrix

## Step 7: CI/CD Integration (Optional)

- [ ] Review GitHub Actions template in `ci/`
- [ ] Configure repository secrets
- [ ] Run pipeline in test mode
- [ ] Verify exit codes and output

## Step 8: Customization

- [ ] Add custom templates to `templates/`
- [ ] Register helper functions in `templates/test_functions/`
- [ ] Configure pattern matching rules
- [ ] Set up custom parsers if needed

## Resources

- User Guide: `docs/user_guide.md`
- CLI Reference: `docs/cli_reference.md`
- Architecture: `docs/architecture_v2.2.md`
- Source Code: `src/`

## Support

For issues or questions, refer to the project documentation or contact the development team.
