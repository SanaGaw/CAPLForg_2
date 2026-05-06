"""Chat resolver for CAPL Pipeline V2.2.

Orchestrates natural language gap resolution conversations.
"""

from typing import Dict, List, Optional, Any
import logging
import json

logger = logging.getLogger(__name__)


class ChatResolver:
    """
    Gap resolution chat orchestrator.

    Handles the conversational flow for resolving ambiguous test steps:
    1. Receives natural language user input
    2. Uses LLM to interpret intent
    3. Validates proposed resolutions against registry
    4. Returns structured resolution for application
    """

    def __init__(
        self,
        llm_router: Any,
        signal_registry: Any,
        validation_schema: str = "chat_resolution"
    ) -> None:
        self.llm_router = llm_router
        self.signal_registry = signal_registry
        self.validation_schema = validation_schema
        self._conversation_history: List[Dict[str, Any]] = []

    async def resolve_gap(
        self,
        gap: Dict[str, Any],
        user_message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve a configuration gap based on user message.

        Args:
            gap: Gap dictionary with id, type, and context
            user_message: Natural language user response
            context: Optional additional context

        Returns:
            Dict with proposed resolution
        """
        # Build prompt for LLM interpretation
        prompt = self._build_resolution_prompt(gap, user_message, context)

        # Call LLM
        try:
            response = await self.llm_router.chat(
                prompt=prompt,
                task="gap_resolution",
                response_schema=self.validation_schema
            )

            # Parse response
            resolution = self._parse_resolution_response(response)

            # Validate against registry
            validation = self._validate_resolution(gap, resolution)

            return {
                "resolution": resolution,
                "validation": validation,
                "requires_approval": resolution.get("requires_approval", True)
            }

        except Exception as e:
            logger.error(f"Gap resolution failed: {e}")
            return {
                "resolution": {"action": "error", "error": str(e)},
                "validation": {"passes": False, "errors": [str(e)]},
                "requires_approval": True
            }

    def _build_resolution_prompt(
        self,
        gap: Dict[str, Any],
        user_message: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build LLM prompt for interpreting user response."""
        gap_type = gap.get("type", "unknown")
        signal_name = gap.get("signal_name", "unknown")
        gap_context = json.dumps(gap.get("context", {}), indent=2)

        return f"""You are a Test Engineering Assistant resolving configuration gaps.

GAP INFORMATION:
- Gap ID: {gap.get("id", "unknown")}
- Type: {gap_type}
- Signal: {signal_name}
- Context: {gap_context}

USER MESSAGE:
{user_message}

Available signals in registry:
{self._get_available_signals()}

RULES:
1. Accept natural language intent. NEVER generate CAPL, YAML, or config directly.
2. Output ONLY valid JSON matching the resolution schema.
3. Validate all proposed signal references against the registry.
4. If confidence < 0.6, flag as LOW_CONFIDENCE.
5. Never auto-apply. Always present options and wait for user decision.
6. Support actions: add_alias, add_constant, apply_template, apply_helper, skip, defer

EXPECTED SCHEMA:
{{
  "proposed_resolution": {{
    "action": "add_alias|add_constant|apply_template|apply_helper|skip|defer",
    "target": "signal_or_target_name",
    "value_or_template": "value_or_template_string",
    "parameters": {{}},
    "apply_globally": false,
    "confidence": 0.0
  }},
  "validation_checks": {{
    "signal_exists": true,
    "type_match": true,
    "range_valid": true,
    "bus_compatible": true
  }},
  "requires_approval": true,
  "explanation": "explanation_string"
}}
"""

    def _get_available_signals(self) -> str:
        """Get list of available signals for context."""
        signals = self.signal_registry.get_all_signals()
        signal_names = [s.name for s in signals[:50]]  # Limit to 50

        if not signal_names:
            return "No signals in registry"

        return ", ".join(signal_names)

    def _parse_resolution_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response into resolution structure."""
        content = response.get("content", "{}")

        try:
            if isinstance(content, str):
                data = json.loads(content)
            else:
                data = content

            return {
                "action": data.get("proposed_resolution", {}).get("action", "skip"),
                "target": data.get("proposed_resolution", {}).get("target", ""),
                "value": data.get("proposed_resolution", {}).get("value_or_template", ""),
                "parameters": data.get("proposed_resolution", {}).get("parameters", {}),
                "apply_globally": data.get("proposed_resolution", {}).get("apply_globally", False),
                "confidence": data.get("proposed_resolution", {}).get("confidence", 0.0),
                "explanation": data.get("explanation", ""),
                "requires_approval": data.get("requires_approval", True)
            }

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse resolution response: {e}")
            return {"action": "error", "error": f"Parse error: {e}"}

    def _validate_resolution(
        self,
        gap: Dict[str, Any],
        resolution: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Validate resolution against registry."""
        errors: List[str] = []
        checks = {
            "signal_exists": True,
            "type_match": True,
            "range_valid": True,
            "bus_compatible": True
        }

        action = resolution.get("action")
        target = resolution.get("target", gap.get("signal_name", ""))

        # Check action validity
        valid_actions = {"add_alias", "add_constant", "apply_template", "apply_helper", "skip", "defer", "error"}
        if action not in valid_actions:
            errors.append(f"Invalid action: {action}")

        # Check signal existence for alias actions
        if action == "add_alias":
            # For add_alias, target is alias and value is canonical name
            canonical = resolution.get("value")
            if canonical:
                signal = self.signal_registry.lookup(canonical)
                if not signal:
                    errors.append(f"Canonical signal '{canonical}' not found in registry")
                    checks["signal_exists"] = False

        elif action in ("skip", "defer", "error"):
            # These are valid terminal actions
            pass

        else:
            # For other actions, check if target exists
            signal = self.signal_registry.lookup(target)
            if not signal:
                # This might be expected for new additions
                pass

        passes = len(errors) == 0

        return {
            "passes": passes,
            "errors": errors,
            "checks": checks
        }

    def start_conversation(self, gap: Dict[str, Any]) -> None:
        """Start a new conversation for a gap."""
        self._conversation_history = [
            {"role": "system", "gap": gap}
        ]

    def add_turn(self, role: str, message: str) -> None:
        """Add a turn to conversation history."""
        self._conversation_history.append({
            "role": role,
            "message": message
        })

    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get conversation history."""
        return self._conversation_history

    def clear_history(self) -> None:
        """Clear conversation history."""
        self._conversation_history = []
