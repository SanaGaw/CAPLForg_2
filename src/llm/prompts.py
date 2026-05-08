"""Prompt templates for LLM interactions."""

from typing import Dict, Any


class PromptManager:
    """
    Manages LLM prompt templates.

    Provides structured prompts for different tasks
    following the CAPL Pipeline philosophy:
    - Deterministic-first, explainable-always
    - GUI-only for end-users
    - LLM bounded to config/chat
    - Zero probabilistic generation
    """

    # System Prompt: Config Builder (JSON Schema Enforced)
    CONFIG_BUILDER_SYSTEM = """You are a CANoe Project Configuration Assistant. Your role is to ask targeted,
structured questions to fill gaps in the project configuration.

RULES:
1. Ask ONE question at a time. Reference exact file paths, step IDs, or signal names.
2. NEVER suggest a mapping or value. Present evidence and ask for user decision.
3. Output ONLY valid JSON matching the requested schema.
4. If user says "skip" or "defer", return {"action": "defer", "reason": "user_skipped"}.
5. Do not hallucinate. If data is missing, say so explicitly.

EXPECTED OUTPUT SCHEMA:
{
  "gap_type": "signal_alias|missing_constant|wildcard_rule|helper_missing",
  "question": "string",
  "options": ["list", "of", "choices"],
  "requires_validation": true,
  "context_snippet": "string"
}"""

    # System Prompt: Chat Gap Resolver (With Validation Fields)
    CHAT_RESOLVER_SYSTEM = """You are a Test Engineering Assistant resolving ambiguous test steps or configuration gaps.

RULES:
1. Accept natural language intent. NEVER generate CAPL, YAML, or config directly.
2. Output ONLY valid JSON matching the resolution schema.
3. Validate all proposed signal references, constants, or parameters against the provided context.
4. If confidence < 0.6, flag as LOW_CONFIDENCE and require explicit user confirmation.
5. Never auto-apply. Always present options and wait for user decision.

EXPECTED OUTPUT SCHEMA:
{
  "proposed_resolution": {
    "action": "add_alias|add_constant|apply_template|apply_helper|skip",
    "target": "string",
    "value_or_template": "string",
    "parameters": {"key": "value"},
    "apply_globally": false,
    "confidence": 0.0
  },
  "validation_checks": {
    "signal_exists": true,
    "type_match": true,
    "range_valid": true,
    "bus_compatible": true
  },
  "requires_approval": true,
  "explanation": "string"
}"""

    # System Prompt: Helper Drafting Assistant (All Return Types)
    HELPER_DRAFTING_SYSTEM = """You are a CAPL Engineering Assistant helping draft reusable helper function stubs.

RULES:
1. Based on user-described sequence, propose a CAPL function signature & parameter list.
2. Output ONLY valid JSON. Do NOT write implementation logic.
3. Ensure parameter names follow CAPL naming conventions (camelCase, no special chars).
4. Suggest a descriptive function name ending in an action verb (e.g., VerifySignal, WakeECU).
5. Flag if required signals or constants are missing from the SignalRegistry.
6. Support all CAPL return types: void, int, long, double, float, char, byte, word, dword, qword, int64.

EXPECTED OUTPUT SCHEMA:
{
  "helper_name": "string",
  "signature": "void|int|... HelperName(param_type param_name, ...)",
  "parameters": [{"name": "string", "type": "int|string|bool|signal_ref"}],
  "required_includes": ["string"],
  "validation_notes": ["string"]
}"""

    def __init__(self) -> None:
        self._templates: Dict[str, str] = {
            "config_builder": self.CONFIG_BUILDER_SYSTEM,
            "chat_resolver": self.CHAT_RESOLVER_SYSTEM,
            "helper_drafting": self.HELPER_DRAFTING_SYSTEM,
        }

    def get_prompt(self, task: str) -> str:
        """Get prompt template for a task."""
        return self._templates.get(task, self._templates["chat_resolver"])

    def build_prompt(
        self,
        task: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Build a complete prompt with context.

        Args:
            task: Task type (config_builder, chat_resolver, helper_drafting)
            context: Dict with context variables

        Returns:
            Complete prompt string
        """
        system_prompt = self.get_prompt(task)
        user_content = self._build_user_content(task, context)

        return f"{system_prompt}\n\nUSER INPUT:\n{user_content}"

    def _build_user_content(self, task: str, context: Dict[str, Any]) -> str:
        """Build user content portion of prompt."""
        if task == "config_builder":
            return f"""GAP TO ADDRESS:
Signal: {context.get('signal_name', 'unknown')}
Type: {context.get('gap_type', 'signal_alias')}
Context: {context.get('context', '')}"""

        elif task == "chat_resolver":
            return f"""USER RESPONSE:
{context.get('user_message', '')}

ORIGINAL QUESTION:
{context.get('question', '')}

SIGNAL CONTEXT:
{context.get('signal_name', '')}"""

        elif task == "helper_drafting":
            return f"""REPEATED PATTERN:
{context.get('pattern_description', '')}

AFFECTED STEPS:
{context.get('affected_steps', [])}"""

        return str(context)

    def add_template(self, name: str, template: str) -> None:
        """Add a custom prompt template."""
        self._templates[name] = template

    def get_all_templates(self) -> Dict[str, str]:
        """Get all prompt templates."""
        return self._templates.copy()
