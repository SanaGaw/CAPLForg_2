"""Traceability exporter for CAPL Pipeline V2.2.

Generates JSON-LD traceability matrices linking CAPL lines
to Excel steps, DBC signals, and configuration decisions.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import logging

logger = logging.getLogger(__name__)


class TraceabilityExporter:
    """
    Generates JSON-LD traceability matrix.

    Creates links between:
    - CAPL source lines and test case steps
    - Signal references and DBC definitions
    - Configuration decisions and final values
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        format: str = "jsonld"
    ) -> None:
        self.output_dir = output_dir or Path("logs")
        self.format = format

    def export_matrix(
        self,
        capl_file: Path,
        test_case: Dict[str, Any],
        signal_registry: Any,
        output_path: Optional[Path] = None
    ) -> Path:
        """
        Export traceability matrix for a single CAPL file.

        Args:
            capl_file: Generated CAPL file path
            test_case: Test case dictionary
            signal_registry: SignalRegistry instance
            output_path: Output path (optional)

        Returns:
            Path to exported matrix file
        """
        from datetime import datetime

        matrix = {
            "@context": "https://capl-pipeline.example.com/traceability/v1",
            "@type": "TraceabilityMatrix",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source": {
                "type": "capl_file",
                "path": str(capl_file)
            },
            "test_case": {
                "id": test_case.get("test_case_id", test_case.get("test_id", "unknown")),
                "description": test_case.get("description", ""),
                "steps": test_case.get("steps", [])
            },
            "traceability": []
        }

        # Build traceability links
        for step in test_case.get("steps", []):
            step_id = step.get("step_id", "")
            step_action = step.get("action", "")

            # Find signals used in this step
            signals = step.get("signal_refs", [])
            for sig_name in signals:
                signal = signal_registry.lookup(sig_name)
                if signal:
                    trace_entry = {
                        "capl_line": f"testStep(\"{step_id}\", ...)",
                        "test_step": step_id,
                        "action": step_action,
                        "signal": {
                            "name": signal.name,
                            "bus_type": signal.bus_type,
                            "env_var": signal.env_var_name,
                            "sys_var_path": signal.sys_var_path,
                            "sources": signal.sources
                        },
                        "links": self._build_signal_links(signal)
                    }
                    matrix["traceability"].append(trace_entry)

        # Write output
        if output_path is None:
            output_path = self.output_dir / "traceability_matrix.jsonld"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(matrix, f, indent=2)

        logger.info(f"Traceability matrix exported: {output_path}")
        return output_path

    def _build_signal_links(self, signal: Any) -> List[Dict[str, str]]:
        """Build traceability links for a signal."""
        links = []

        # Link to each source
        for source in signal.sources:
            detail = signal.source_details.get(source)
            if detail:
                links.append({
                    "source": source,
                    "file": detail.file,
                    "line": str(detail.line) if detail.line else "N/A"
                })

        return links

    def export_batch(
        self,
        capl_files: List[Path],
        test_cases: List[Dict[str, Any]],
        signal_registry: Any
    ) -> Path:
        """
        Export traceability matrix for multiple CAPL files.

        Returns:
            Path to combined matrix file
        """
        from datetime import datetime

        combined_matrix = {
            "@context": "https://capl-pipeline.example.com/traceability/v1",
            "@type": "TraceabilityMatrixCollection",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "count": len(capl_files),
            "matrices": []
        }

        for capl_file, test_case in zip(capl_files, test_cases):
            matrix = self._export_single_matrix(capl_file, test_case, signal_registry)
            combined_matrix["matrices"].append(matrix)

        output_path = self.output_dir / "traceability_matrix_batch.jsonld"

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(combined_matrix, f, indent=2)

        logger.info(f"Batch traceability exported: {output_path}")
        return output_path

    def _export_single_matrix(
        self,
        capl_file: Path,
        test_case: Dict[str, Any],
        signal_registry: Any
    ) -> Dict[str, Any]:
        """Export a single matrix as dict (for batch processing)."""
        from datetime import datetime

        matrix = {
            "source": str(capl_file),
            "test_case_id": test_case.get("test_case_id"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "traceability": []
        }

        for step in test_case.get("steps", []):
            signals = step.get("signal_refs", [])
            for sig_name in signals:
                signal = signal_registry.lookup(sig_name)
                if signal:
                    matrix["traceability"].append({
                        "step": step.get("step_id"),
                        "signal": sig_name,
                        "sources": signal.sources
                    })

        return matrix

    def generate_html_report(self, matrix_path: Path) -> Path:
        """
        Generate HTML visualization of traceability matrix.

        Args:
            matrix_path: Path to JSON-LD matrix file

        Returns:
            Path to HTML report
        """
        from datetime import datetime

        matrix = json.loads(matrix_path.read_text())

        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Traceability Report - {datetime.utcnow().strftime('%Y-%m-%d')}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background-color: #2c3e50; color: white; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        .source-badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
            margin-right: 4px;
        }}
        .source-dbc {{ background: #3498db; color: white; }}
        .source-vsysvar {{ background: #27ae60; color: white; }}
        .source-can_file {{ background: #f39c12; color: white; }}
        .source-sto_spec {{ background: #9b59b6; color: white; }}
    </style>
</head>
<body>
    <h1>CAPL Pipeline Traceability Report</h1>
    <p>Generated: {datetime.utcnow().isoformat()}</p>

    <h2>Test Case: {matrix.get('test_case', {}).get('id', 'Unknown')}</h2>
    <p>{matrix.get('test_case', {}).get('description', '')}</p>

    <h3>Traceability Matrix</h3>
    <table>
        <tr>
            <th>Step ID</th>
            <th>Action</th>
            <th>Signal</th>
            <th>Bus Type</th>
            <th>Env Var</th>
            <th>Sources</th>
        </tr>
"""

        for entry in matrix.get("traceability", []):
            sig = entry.get("signal", {})
            sources_html = ""
            for src in sig.get("sources", []):
                sources_html += f'<span class="source-badge source-{src}">{src}</span>'

            html += f"""        <tr>
            <td>{entry.get('test_step', '')}</td>
            <td>{entry.get('action', '')}</td>
            <td>{sig.get('name', '')}</td>
            <td>{sig.get('bus_type', 'N/A')}</td>
            <td>{sig.get('env_var', 'N/A')}</td>
            <td>{sources_html}</td>
        </tr>
"""

        html += """    </table>
</body>
</html>"""

        output_path = matrix_path.with_suffix('.html')
        output_path.write_text(html, encoding='utf-8')

        logger.info(f"HTML report generated: {output_path}")
        return output_path
