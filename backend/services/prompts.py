"""
Prompt library.

Every AI call reads its wording from ``prompts/`` (see ``prompts/README.md``)
rather than from an inline string, so prompts can be reviewed and tuned without
touching Python.

Layout::

    prompts/system/<call>.md   persona and standing rules
    prompts/user/<call>.md     the task and the values for one call

Templates use ``$name`` placeholders (``string.Template``), which keeps the JSON
schema braces in ``system/roadmap.md`` literal instead of doubled.
"""

import hashlib
from pathlib import Path
from string import Template
from typing import Any

from app_logging import get_logger

log = get_logger("careercompass.prompts")

#: Repository-relative root of the prompt files (``backend/prompts``).
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


class PromptNotFoundError(FileNotFoundError):
    """Raised when a template referenced by the app is missing from disk."""


def load_text(relative_path: str) -> str:
    """Reads one template, failing loudly when it is absent.

    Prompts are required, not optional: a missing file is a packaging mistake we
    want to hear about immediately rather than silently degrade the AI call.
    """
    path = PROMPTS_DIR / relative_path
    if not path.is_file():
        raise PromptNotFoundError(
            f"Prompt template '{relative_path}' not found under {PROMPTS_DIR}."
        )
    return path.read_text(encoding="utf-8")


def render(relative_path: str, **values: Any) -> str:
    """Loads a template and substitutes its ``$placeholders``.

    ``Template.substitute`` (not ``safe_substitute``) is deliberate: a typo in a
    template or a forgotten value should fail here rather than ship a prompt with
    a literal ``$role_title`` still in it. Values are inserted verbatim, so a
    ``$`` inside a substituted value is never treated as a placeholder.
    """
    return Template(load_text(relative_path)).substitute(**values)


def fingerprint(*relative_paths: str) -> str:
    """A short, stable hash of one or more templates.

    Prompts are edited as files, so a diff alone cannot tell you which wording was
    live when an artifact was produced. Saved AI output records this fingerprint
    instead, which makes "same model, same prompt, same plan" checkable after the
    fact.
    """
    digest = hashlib.sha256()
    for relative_path in sorted(relative_paths):
        digest.update(relative_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(load_text(relative_path).encode("utf-8"))
    return digest.hexdigest()[:12]
