"""
Local development runner. Reads client project path from CAPL_FORGE_CFG
environment variable. This keeps client paths out of the repo.
"""
import os
import sys
from pathlib import Path
from canoe_cfg_inspector import CfgInspector
from kb_builder import build_knowledge_base


def main():
    cfg_env = os.environ.get("CAPL_FORGE_CFG")
    if not cfg_env:
        print("ERROR: set CAPL_FORGE_CFG to the path of your .cfg file")
        print("Example (PowerShell):")
        print('  $env:CAPL_FORGE_CFG = "C:\\path\\to\\project.cfg"')
        sys.exit(1)

    cfg_path = Path(cfg_env)
    if not cfg_path.exists():
        print(f"ERROR: cfg file not found: {cfg_path}")
        sys.exit(1)

    local_dir = Path(__file__).parent / "local"
    local_dir.mkdir(exist_ok=True)
    db_path = local_dir / "dcu_knowledge.db"

    print(f"Inspecting: {cfg_path.name}")
    result = CfgInspector(log=print).inspect(cfg_path)

    print(f"Building KB: {db_path}")
    summary = build_knowledge_base(result, str(db_path), log=print)
    print(f"Done. {summary['row_counts']}")


if __name__ == "__main__":
    main()
