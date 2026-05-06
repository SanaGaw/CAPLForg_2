"""Configuration builder for CAPL Pipeline V2.2.

LLM-guided Q&A orchestrator for resolving configuration gaps.
"""

from typing import Any, Dict, List, Optional, Callable, Awaitable
from dataclasses import dataclass, field
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class GapQuestion:
    """A structured question to present to the user about a configuration gap."""
    gap_id: str
    gap_type: str           # "signal_alias" | "missing_constant" | "wildcard_rule" | "helper_missing"
    question: str
    options: List[str] = field(default_factory=list)
    context_snippet: str = ""
    requires_validation: bool = True


@dataclass
class UserResponse:
    """User's response to a gap question, as interpreted by the LLM."""
    gap_id: str
    action: str             # "add_alias" | "add_constant" | "apply_template" | "apply_helper" | "defer" | "skip"
    target: str = ""
    value: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    apply_globally: bool = False
    confidence: float = 0.0
    explanation: str = ""


@dataclass
class GapResolution:
    """Result of resolving a single gap."""
    gap_id: str
    status: str             # "resolved" | "deferred" | "blocked" | "failed_validation"
    resolution: Optional[UserResponse] = None
    validation_errors: List[str] = field(default_factory=list)
    iterations_used: int = 0


@dataclass
class ValidationResult:
    """Result of validating a proposed resolution."""
    passes: bool
    errors: List[str] = field(default_factory=list)


class ConfigBuilderOrchestrator:
    """
    Multi-turn gap resolution orchestrator.

    Flow per gap:
      1. System identifies gap
      2. LLM generates structured question (using Config Builder prompt template)
      3. Question presented to user via WebSocket/GUI
      4. User responds in natural language
      5. LLM interprets user response into structured resolution (using Chat Resolver prompt template)
      6. System validates resolution against registry
      7. If valid -> apply; if not -> re-prompt with error context

    The LLM NEVER directly resolves gaps. It only helps formulate questions
    and interpret user responses.
    """

    def __init__(
        self,
        registry: Any,              # SignalRegistry
        llm_client: Any,            # LLMRouter
        ui_adapter: Any,             # WebSocket/GUI adapter
        schema_dir: str = "config_schemas",
        max_iterations: Optional[int] = None,
        max_retries_per_gap: int = 3,
    ) -> None:
        self.registry = registry
        self.llm_client = llm_client
        self.ui_adapter = ui_adapter
        self.schema_dir = schema_dir
        self.max_iterations = max_iterations or int(
            os.getenv("CONFIG_BUILDER_MAX_ITERATIONS", "100")
        )
        self.max_retries_per_gap = max_retries_per_gap

    async def run_conversation_loop(self, validation_report: Dict) -> Dict:
        """
        Main async loop for Web UI config building.
        Exits on: all gaps resolved, max_iterations reached, or user abort.
        """
        gaps = self.identify_gaps(validation_report)
        resolutions: List[GapResolution] = []

        iteration = 0
        while gaps and iteration < self.max_iterations:
            iteration += 1

            for gap in gaps[:]:  # Iterate over copy to allow removal
                retries = 0
                resolved = False

                while retries < self.max_retries_per_gap and not resolved:
                    # Step 1: LLM generates structured question for this gap
                    question: GapQuestion = await self.generate_gap_question(gap)

                    # Step 2: Present question to user via GUI, await natural language response
                    raw_user_response = await self.ui_adapter.ask_user(question)

                    # Step 3: Check for user defer/skip
                    if raw_user_response.get("action") in ("defer", "skip"):
                        resolutions.append(GapResolution(
                            gap_id=gap.get("id", ""),
                            status="deferred",
                        ))
                        gaps.remove(gap)
                        break

                    # Step 4: LLM interprets user response into structured resolution
                    proposed: UserResponse = await self.interpret_user_response(
                        gap, question, raw_user_response
                    )

                    # Step 5: Validate proposed resolution against registry
                    validation = self.validate_resolution(gap, proposed)

                    if validation.passes:
                        # Step 6: Apply resolution
                        self.apply_resolution(gap, proposed)
                        resolutions.append(GapResolution(
                            gap_id=gap.get("id", ""),
                            status="resolved",
                            resolution=proposed,
                            iterations_used=retries + 1,
                        ))
                        gaps.remove(gap)
                        resolved = True
                    else:
                        retries += 1
                        # Re-prompt with validation error context
                        gap["_validation_errors"] = validation.errors
                        gap["_retries"] = retries
                        logger.warning(
                            f"Gap {gap.get('id')} validation failed "
                            f"(attempt {retries}/{self.max_retries_per_gap}): "
                            f"{validation.errors}"
                        )

                if not resolved and retries >= self.max_retries_per_gap:
                    resolutions.append(GapResolution(
                        gap_id=gap.get("id", ""),
                        status="failed_validation",
                        validation_errors=gap.get("_validation_errors", []),
                        iterations_used=retries,
                    ))
                    gaps.remove(gap)

            # Re-validate remaining gaps after batch update
            if gaps:
                validation_report = self.registry.export_report()
                gaps = self.identify_gaps(validation_report)

        resolved_count = sum(1 for r in resolutions if r.status == "resolved")
        deferred_count = sum(1 for r in resolutions if r.status == "deferred")
        failed_count = sum(1 for r in resolutions if r.status == "failed_validation")

        return {
            "resolved": resolved_count,
            "deferred": deferred_count,
            "failed_validation": failed_count,
            "remaining": len(gaps),
            "iterations_used": iteration,
            "status": "complete" if not gaps else "partial",
            "resolutions": resolutions,
        }

    async def generate_gap_question(self, gap: Dict) -> GapQuestion:
        """Use LLM (Config Builder prompt) to generate a structured question."""
        prompt = self.build_question_prompt(gap)
        response = await self.llm_client.chat(
            prompt,
            task="gap_resolution",
            response_schema="config_builder_question",
        )
        return GapQuestion(
            gap_id=gap.get("id", ""),
            gap_type=response.get("gap_type", "unknown"),
            question=response.get("question", ""),
            options=response.get("options", []),
            context_snippet=response.get("context_snippet", ""),
            requires_validation=response.get("requires_validation", True),
        )

    async def interpret_user_response(
        self, gap: Dict, question: GapQuestion, raw_response: Dict
    ) -> UserResponse:
        """Use LLM (Chat Resolver prompt) to interpret user's natural language response."""
        prompt = self.build_interpretation_prompt(gap, question, raw_response)
        response = await self.llm_client.chat(
            prompt,
            task="gap_resolution",
            response_schema="chat_resolution",
        )
        return UserResponse(
            gap_id=gap.get("id", ""),
            action=response.get("proposed_resolution", {}).get("action", "skip"),
            target=response.get("proposed_resolution", {}).get("target", ""),
            value=response.get("proposed_resolution", {}).get("value_or_template", ""),
            parameters=response.get("proposed_resolution", {}).get("parameters", {}),
            apply_globally=response.get("proposed_resolution", {}).get("apply_globally", False),
            confidence=response.get("proposed_resolution", {}).get("confidence", 0.0),
            explanation=response.get("explanation", ""),
        )

    def identify_gaps(self, validation_report: Dict) -> List[Dict]:
        """Extract unresolved gaps from validation report."""
        gaps: List[Dict] = []

        for signal_name in validation_report.get("gap_signals", []):
            gaps.append({
                "id": f"gap_{signal_name}",
                "type": "signal_alias",
                "signal_name": signal_name,
            })

        return gaps

    def build_question_prompt(self, gap: Dict) -> str:
        """Build LLM prompt for question generation."""
        return f"""You are a CANoe Project Configuration Assistant. Your role is to ask targeted,
structured questions to fill gaps in the project configuration.

GAPS IDENTIFIED:
- Signal: {gap.get('signal_name', 'unknown')}
- Type: {gap.get('type', 'unknown')}

CONTEXT:
{gap.get('context', '')}

RULES:
1. Ask ONE question at a time. Reference exact file paths, step IDs, or signal names.
2. NEVER suggest a mapping or value. Present evidence and ask for user decision.
3. Output ONLY valid JSON matching the requested schema.
4. If user says "skip" or "defer", return {{"action": "defer", "reason": "user_skipped"}}.
5. Do not hallucinate. If data is missing, say so explicitly.
"""

    def build_interpretation_prompt(
        self, gap: Dict, question: GapQuestion, raw_response: Dict
    ) -> str:
        """Build LLM prompt for response interpretation."""
        return f"""You are a Test Engineering Assistant resolving ambiguous test steps or configuration gaps.

ORIGINAL QUESTION:
{question.question}

OPTIONS:
{question.options}

USER RESPONSE:
{raw_response.get('message', '')}

SIGNAL CONTEXT:
{gap.get('signal_name', '')}

RULES:
1. Accept natural language intent. NEVER generate CAPL, YAML, or config directly.
2. Output ONLY valid JSON matching the resolution schema.
3. Validate all proposed signal references, constants, or parameters against the provided context.
4. If confidence < 0.6, flag as LOW_CONFIDENCE and require explicit user confirmation.
5. Never auto-apply. Always present options and wait for user decision.
"""

    def validate_resolution(self, gap: Dict, proposed: UserResponse) -> ValidationResult:
        """Validate proposed resolution against registry."""
        errors: List[str] = []

        # Check if target signal exists
        target = proposed.target or gap.get("signal_name", "")
        if target:
            signal = self.registry.lookup(target)
            if signal is None and proposed.action not in ("add_alias", "add_constant"):
                errors.append(f"Signal '{target}' not found in registry")

        # Validate action type
        valid_actions = {"add_alias", "add_constant", "apply_template", "apply_helper", "skip", "defer"}
        if proposed.action not in valid_actions:
            errors.append(f"Invalid action: {proposed.action}")

        return ValidationResult(passes=len(errors) == 0, errors=errors)

    def apply_resolution(self, gap: Dict, resolution: UserResponse) -> None:
        """Apply validated resolution to the registry."""
        action = resolution.action
        target = resolution.target or gap.get("signal_name", "")

        if action == "add_alias":
            self.registry.add_alias(
                alias=target,
                canonical_name=resolution.value,
                source="config_builder"
            )
        elif action == "add_constant":
            # Register constant in registry
            pass

        logger.info(f"Applied resolution for gap {gap.get('id')}: {action} on {target}")
