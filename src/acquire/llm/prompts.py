from __future__ import annotations

from pathlib import Path

from jinja2 import Template

from acquire.config import CONFIG_DIR


def load_prompt(name: str, **kwargs) -> str:
    """Load a prompt template from config/prompts/{name}.md and render with kwargs."""
    path = CONFIG_DIR / "prompts" / f"{name}.md"
    template_text = path.read_text()
    template = Template(template_text)
    return template.render(**kwargs)
