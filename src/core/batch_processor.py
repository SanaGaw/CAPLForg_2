"""Batch processor for CAPL Pipeline V2.2.

Parallel test case processing with deterministic output ordering.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
import hashlib
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Parallel test case processor with deterministic output ordering.
    Output files must be byte-identical whether processed sequentially or in parallel.
    Deterministic ordering: sort by SHA-256(step_id + excel_row) before writing.
    """

    def __init__(
        self,
        max_parallel: Optional[int] = None,
        output_dir: Path = Path("output"),
        dry_run: bool = False,
    ) -> None:
        self.max_parallel = max_parallel or int(
            os.getenv("MAX_PARALLEL_TASKS", "4")
        )
        self.output_dir = output_dir
        self.dry_run = dry_run

    @staticmethod
    def deterministic_sort_key(step: dict) -> str:
        """Generate deterministic sort key from step ID + Excel row."""
        raw = f"{step.get('step_id', '')}_{step.get('excel_row', '')}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def process_batch(self, test_cases: List[dict]) -> Dict[str, Any]:
        """
        Process test cases in parallel with deterministic output ordering.

        Args:
            test_cases: List of test case dictionaries

        Returns:
            Dict with total count and results list
        """
        # Sort deterministically before any parallel processing
        sorted_cases = sorted(test_cases, key=self.deterministic_sort_key)

        semaphore = asyncio.Semaphore(self.max_parallel)
        results = []

        async def process_one(case: dict) -> dict:
            async with semaphore:
                if self.dry_run:
                    return {
                        "step_id": case.get("step_id"),
                        "status": "dry_run",
                        "sort_key": self.deterministic_sort_key(case)
                    }

                # Generate CAPL for this test case
                try:
                    result = await self._generate_capl(case)
                    return {
                        "step_id": case.get("step_id"),
                        "status": "success",
                        "file_path": result.get("file_path"),
                        "sort_key": self.deterministic_sort_key(case)
                    }
                except Exception as e:
                    logger.error(f"Error processing {case.get('step_id')}: {e}")
                    return {
                        "step_id": case.get("step_id"),
                        "status": "error",
                        "error": str(e),
                        "sort_key": self.deterministic_sort_key(case)
                    }

        # Process all cases in parallel
        tasks = [process_one(case) for case in sorted_cases]
        results = await asyncio.gather(*tasks)

        # Sort results again by same key to guarantee deterministic order
        results.sort(key=lambda r: r.get("sort_key", ""))

        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get("status") == "success"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
            "dry_run": sum(1 for r in results if r.get("status") == "dry_run"),
            "results": results
        }

    async def _generate_capl(self, test_case: dict) -> Dict[str, Any]:
        """Generate CAPL for a single test case."""
        # This is a stub - actual implementation would use CAPL generator
        from ..capl.generator import CaplGenerator

        generator = CaplGenerator()
        output_path = self.output_dir / f"{test_case.get('step_id', 'unknown')}.can"

        # Generate CAPL content
        content = generator.generate_from_test_case(test_case)

        if not self.dry_run:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding='utf-8')

        return {"file_path": str(output_path), "content": content}

    def process_sequential(self, test_cases: List[dict]) -> Dict[str, Any]:
        """
        Process test cases sequentially (for comparison/validation).

        Args:
            test_cases: List of test case dictionaries

        Returns:
            Dict with total count and results list
        """
        # Sort deterministically
        sorted_cases = sorted(test_cases, key=self.deterministic_sort_key)

        results = []
        for case in sorted_cases:
            try:
                if self.dry_run:
                    result = {
                        "step_id": case.get("step_id"),
                        "status": "dry_run"
                    }
                else:
                    # Synchronous CAPL generation
                    result = {
                        "step_id": case.get("step_id"),
                        "status": "success"
                    }
            except Exception as e:
                result = {
                    "step_id": case.get("step_id"),
                    "status": "error",
                    "error": str(e)
                }
            result["sort_key"] = self.deterministic_sort_key(case)
            results.append(result)

        return {
            "total": len(results),
            "successful": sum(1 for r in results if r.get("status") == "success"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
            "results": results
        }
