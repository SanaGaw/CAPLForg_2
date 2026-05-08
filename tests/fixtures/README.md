# Synthetic Test Fixtures

All fixture files use synthetic names — no real automotive data.

## Naming Policy
- Signals: `FOO_SIGNAL_X`, `BAR_SIGNAL_Y`
- Messages: `TestFrame_42`, `DiagFrame_01`
- DIDs: `0xDEAD`, `0xBEEF`
- Env vars: `EV_TEST_SIGNAL`, `EV_ANOTHER_VAR`
- Sysvars: `sysvar::Test::Speed`

## Files
| File | Format | Purpose |
|------|--------|---------|
| synthetic.cfg | CANoe config | Reference resolution testing |
| FOO_SIGNAL_X.dbc | DBC | Message/signal extraction |
| env_only.dbc | DBC | Environment variable extraction |
| DEAD.cdd | CDD | Diagnostic ID extraction |
| synthetic.vsysvar | VSYSVAR | System variable extraction |
| synthetic.can | CAPL | Handler/usage extraction |
| test_plan.xlsx | Excel | Column mapping testing |
