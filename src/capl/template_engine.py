"""Jinja2 template engine for CAPL Pipeline V2.2.

Sandboxed template environment for CAPL code generation.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any
from jinja2 import Environment, Template, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from jinja2.exceptions import TemplateSyntaxError, SecurityError
import logging

logger = logging.getLogger(__name__)


class JinjaEnvironment:
    """
    Sandboxed Jinja2 environment for CAPL templates.

    Uses SandboxedEnvironment to prevent arbitrary Python execution.
    StrictUndefined ensures undefined variables raise errors (no silent defaults).
    """

    def __init__(self, template_dir: Optional[Path] = None) -> None:
        self.template_dir = template_dir or Path("templates")

        # Create sandboxed environment with strict undefined
        self.env = SandboxedEnvironment(
            loader=None,  # We'll load templates explicitly
            autoescape=False,  # CAPL is not HTML
            undefined=StrictUndefined,  # Raise error on undefined
            extensions=[
                'jinja2.ext.do',  # Loop controls
            ]
        )

        # Security: Block potentially dangerous operations
        self._blocked_filters = ['safe', 'xmlattr']  # We don't need these for CAPL

    def compile_template(self, template_str: str) -> Template:
        """
        Compile a template string.

        Args:
            template_str: Template content

        Returns:
            Compiled Template object
        """
        try:
            return self.env.from_string(template_str)
        except TemplateSyntaxError as e:
            logger.error(f"Template syntax error: {e}")
            raise

    def render(self, template_str: str, context: Dict[str, Any]) -> str:
        """
        Render a template with context.

        Args:
            template_str: Template content
            context: Variables to render with

        Returns:
            Rendered output
        """
        template = self.compile_template(template_str)
        return template.render(**context)


class TemplateEngine:
    """
    High-level template engine for CAPL generation.

    Manages template loading, compilation, and rendering.
    Ensures deterministic output (no random functions, timestamps, etc.).
    """

    # Built-in CAPL templates
    DEFAULT_TEMPLATES = {
        "test_case": """
/*! Test Case: {{ test_case_id }}
 *  Description: {{ description }}
 *  Generated: {{ generation_timestamp }}
 */

#include <{{ helper_include }}>
#include "helpers.cin"

{% for include in includes %}
#include "{{ include }}"
{% endfor %}

variables {
    {% for var in variables %}
    {{ var.type }} {{ var.name }}{% if var.initial %} = {{ var.initial }}{% endif %};
    {% endfor %}
}

void {{ test_function_name }}(void) {
    {% for step in test_steps %}
    testStep("{{ step.step_id }}", "{{ step.action }}");
    {% if step.signal %}
    {% if step.action_type == 'set' %}
    putValue({{ step.env_var }}, ${{ step.signal }});
    {% elif step.action_type == 'check' %}
    {% if step.expected_value %}
    if ({{ step.env_var }} != ${{ step.signal }}) {
        TestReportAddFailure("{{ step.description }}: Expected ${{ step.signal }}");
    }
    {% endif %}
    {% endif %}
    {% endif %}
    {% endfor %}
}
""",
        "signal_verify": """
/*! Verify Signal: {{ signal_name }}
 *  Expected: {{ expected_value }}
 */

{% if env_var %}
if ({{ env_var }} != {{ expected_value }}) {
    TestReportAddFailure("Signal {{ signal_name }} verification failed");
}
{% endif %}
""",
        "ecus_wakeup": """
/*! ECU Wake-up Sequence */

void ECUWakeUp(void) {
    {% for ecu in ecus %}
    ${{ ecu.signal }} = 1;
    putValue({{ ecu.env_var }}, 1);
    testWaitForTimeout(100);
    {% endfor %}
}
"""
    }

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        helper_includes: Optional[List[str]] = None
    ) -> None:
        self.jinja_env = JinjaEnvironment(template_dir)
        self.template_dir = template_dir or Path("templates/test_functions")
        self.helper_includes = helper_includes or ["helpers.cin"]
        self._template_cache: Dict[str, Template] = {}

    def load_template(self, template_name: str) -> str:
        """
        Load a template by name.

        Args:
            template_name: Name of template (with or without .can extension)

        Returns:
            Template content string
        """
        # Check built-in templates first
        if template_name in self.DEFAULT_TEMPLATES:
            return self.DEFAULT_TEMPLATES[template_name]

        # Try loading from file
        template_path = self.template_dir / template_name
        if not template_path.suffix:
            template_path = template_path.with_suffix('.can')

        if template_path.exists():
            return template_path.read_text(encoding='utf-8')

        raise FileNotFoundError(f"Template not found: {template_name}")

    def render(
        self,
        template_name: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Render a template with context.

        Args:
            template_name: Name of template to render
            context: Variables for template

        Returns:
            Rendered CAPL code
        """
        # Ensure deterministic timestamp
        if 'generation_timestamp' not in context:
            context['generation_timestamp'] = 'N/A (deterministic build)'

        # Add helper includes
        if 'includes' not in context:
            context['includes'] = self.helper_includes

        template_str = self.load_template(template_name)
        return self.jinja_env.render(template_str, context)

    def render_from_string(
        self,
        template_str: str,
        context: Dict[str, Any]
    ) -> str:
        """
        Render a template from string.

        Args:
            template_str: Template content
            context: Variables for template

        Returns:
            Rendered CAPL code
        """
        return self.jinja_env.render(template_str, context)

    def validate_template(self, template_str: str) -> tuple[bool, Optional[str]]:
        """
        Validate template syntax.

        Args:
            template_str: Template content

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self.jinja_env.compile_template(template_str)
            return True, None
        except TemplateSyntaxError as e:
            return False, str(e)
        except SecurityError as e:
            return False, f"Security error: {e}"

    def get_available_templates(self) -> List[str]:
        """Get list of available template names."""
        templates = list(self.DEFAULT_TEMPLATES.keys())

        if self.template_dir.exists():
            for path in self.template_dir.glob('*.can'):
                name = path.stem
                if name not in templates:
                    templates.append(name)

        return sorted(templates)
