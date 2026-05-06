"""Offline questionnaire resolver for CAPL Pipeline V2.2.

Provides a questionnaire-based fallback when LLM is unavailable.
Used in compliance mode when network is blocked.
"""

from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)


@dataclass
class QuestionnaireQuestion:
    """A question in the offline questionnaire."""
    question_id: str
    question: str
    options: List[str] = field(default_factory=list)
    default_value: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuestionnaireResponse:
    """Response to a questionnaire question."""
    question_id: str
    selected_option: Optional[str] = None
    custom_value: Optional[str] = None
    skipped: bool = False


class OfflineResolver:
    """
    Offline questionnaire-based gap resolution.

    This resolver works without LLM by presenting structured
    questions to the user and applying predefined resolution patterns.
    """

    def __init__(self) -> None:
        self._questionnaire_templates: Dict[str, List[QuestionnaireQuestion]] = {}

    def register_questionnaire(
        self,
        gap_type: str,
        questions: List[QuestionnaireQuestion]
    ) -> None:
        """Register a questionnaire template for a gap type."""
        self._questionnaire_templates[gap_type] = questions

    def get_questionnaire(
        self,
        gap_type: str,
        context: Dict[str, Any]
    ) -> List[QuestionnaireQuestion]:
        """
        Get the questionnaire for a gap type.

        Returns:
            List of QuestionnaireQuestion objects
        """
        questions = self._questionnaire_templates.get(gap_type, [])

        # Generate dynamic questions based on context
        if gap_type == "signal_alias":
            signal_name = context.get("signal_name", "unknown")
            questions = [
                QuestionnaireQuestion(
                    question_id=f"{signal_name}_type",
                    question=f"What type of signal is '{signal_name}'?",
                    options=["CAN", "LIN", "FLEXRAY", "ETHERNET"],
                    default_value="CAN"
                ),
                QuestionnaireQuestion(
                    question_id=f"{signal_name}_alias",
                    question=f"What is the canonical name for '{signal_name}'?",
                    options=[],
                    default_value=signal_name
                ),
            ]

        elif gap_type == "missing_constant":
            constant_name = context.get("constant_name", "unknown")
            questions = [
                QuestionnaireQuestion(
                    question_id=f"{constant_name}_value",
                    question=f"What value should '{constant_name}' have?",
                    options=[],
                    default_value="0"
                ),
            ]

        return questions

    def resolve_with_questionnaire(
        self,
        gap: Dict[str, Any],
        responses: List[QuestionnaireResponse]
    ) -> Dict[str, Any]:
        """
        Resolve a gap using questionnaire responses.

        Args:
            gap: Gap dictionary
            responses: List of user responses

        Returns:
            Resolution dictionary
        """
        gap_type = gap.get("type", "unknown")
        responses_by_id = {r.question_id: r for r in responses}

        if gap_type == "signal_alias":
            # Find alias response
            signal_name = gap.get("signal_name", "")
            type_response = None
            alias_response = None

            for q_id, response in responses_by_id.items():
                if "_type" in q_id:
                    type_response = response
                elif "_alias" in q_id:
                    alias_response = response

            canonical_name = alias_response.custom_value if alias_response else signal_name
            bus_type = type_response.selected_option if type_response else "CAN"

            return {
                "action": "add_alias",
                "target": signal_name,
                "value": canonical_name,
                "parameters": {"bus_type": bus_type},
                "apply_globally": False
            }

        elif gap_type == "missing_constant":
            constant_name = gap.get("constant_name", "")
            value_response = responses_by_id.get(f"{constant_name}_value")

            return {
                "action": "add_constant",
                "target": constant_name,
                "value": value_response.custom_value if value_response else "0",
                "parameters": {},
                "apply_globally": False
            }

        else:
            return {
                "action": "skip",
                "target": gap.get("signal_name", ""),
                "value": "",
                "parameters": {},
                "apply_globally": False
            }

    def generate_questionnaire_form(
        self,
        gaps: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Generate questionnaire forms for multiple gaps.

        Returns:
            List of form dictionaries
        """
        forms = []

        for gap in gaps:
            gap_type = gap.get("type", "unknown")
            context = {
                "signal_name": gap.get("signal_name", ""),
                "constant_name": gap.get("constant_name", ""),
            }

            questions = self.get_questionnaire(gap_type, context)

            forms.append({
                "gap_id": gap.get("id", ""),
                "gap_type": gap_type,
                "questions": [
                    {
                        "id": q.question_id,
                        "question": q.question,
                        "options": q.options,
                        "default": q.default_value
                    }
                    for q in questions
                ]
            })

        return forms

    def apply_batch_resolutions(
        self,
        gaps: List[Dict[str, Any]],
        responses: List[List[QuestionnaireResponse]],
        registry: Any
    ) -> Dict[str, Any]:
        """
        Apply resolutions for multiple gaps in batch.

        Returns:
            Dict with results summary
        """
        resolved = 0
        skipped = 0
        failed = 0

        for gap, gap_responses in zip(gaps, responses):
            if any(r.skipped for r in gap_responses):
                skipped += 1
                continue

            try:
                resolution = self.resolve_with_questionnaire(gap, gap_responses)
                self._apply_resolution(resolution, registry)
                resolved += 1
            except Exception as e:
                logger.error(f"Failed to apply resolution for {gap.get('id')}: {e}")
                failed += 1

        return {
            "total": len(gaps),
            "resolved": resolved,
            "skipped": skipped,
            "failed": failed
        }

    def _apply_resolution(self, resolution: Dict[str, Any], registry: Any) -> None:
        """Apply a resolution to the registry."""
        action = resolution.get("action")
        target = resolution.get("target", "")
        value = resolution.get("value", "")

        if action == "add_alias":
            registry.add_alias(
                alias=target,
                canonical_name=value,
                source="offline_questionnaire"
            )
        elif action == "add_constant":
            # Register constant
            pass

        logger.info(f"Applied offline resolution: {action} for {target}")
