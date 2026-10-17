"""Scrubbing for everything a client sends that ends up inside a prompt.

The API is stateless and guest-friendly, so the roadmap, the match explanation and
the copilot all receive the candidate's own answers back from the browser rather
than reading them from the database. Those values are *data*, never instructions —
but they are interpolated into prompt text (the copilot's persona is a system
instruction), so a crafted value could otherwise smuggle a new instruction block
into the model's context.

Two rules keep that honest:

* free text is collapsed to a single line, stripped of control characters and
  length-capped, so it cannot open a new "Guidelines:" section; and
* anything that is conceptually a short chip (interests, skills) is reduced to a
  plain label, so even a single-line instruction loses the punctuation it would
  need to read as one.

Legitimate answers are unaffected: every real chip ("SQL / MySQL / PostgreSQL",
"C#/.NET", "CI/CD"), city and goal length passes through byte-identical.
"""
import re

# Control characters, excluding tab/newline/carriage-return, which the whitespace
# collapse below turns into ordinary spaces.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")
# What a real chip is made of: words, and the punctuation tech names use. Anything
# else (quotes, backticks, braces, colons that would read as a new section, …) is
# dropped rather than escaped, because a chip never legitimately contains it.
_LABEL_ALLOWED = re.compile(r"[^0-9A-Za-z +#./&()\-_,']")


def _text(value) -> str:
    """Coerces to text without letting a container explode into a repr of itself."""
    if isinstance(value, str):
        return value
    if value is None or isinstance(value, (int, float, bool)):
        return "" if value is None else str(value)
    return ""


def single_line(value, limit: int = 120) -> str:
    """One trimmed line, no control characters, at most ``limit`` characters."""
    text = _WHITESPACE.sub(" ", _CONTROL.sub(" ", _text(value))).strip()
    return text[:limit]


def label(value, limit: int = 60) -> str:
    """A single chip, reduced to the characters a real chip is made of."""
    return _LABEL_ALLOWED.sub("", single_line(value, limit)).strip()


def labels(values, limit: int = 12) -> list:
    """Cleanses a list of chips, dropping blanks and capping how many survive."""
    if not isinstance(values, (list, tuple)):
        return []
    cleaned = []
    for value in list(values)[:limit]:
        text = label(value)
        if text:
            cleaned.append(text)
    return cleaned


def message(value, limit: int = 4000) -> str:
    """Chat text: newlines are meaningful (code blocks), so only cap and de-control."""
    return _CONTROL.sub("", _text(value))[:limit]


def chat_history(messages, max_turns: int = 20, limit: int = 4000) -> list:
    """Keeps the last ``max_turns`` well-formed turns, dropping anything malformed.

    The history is replayed to the model as its own past turns, so an entry that is
    not a real user/model turn (or that omits its text) must never reach the SDK as
    a ``KeyError`` or as an unexpected role. Gemini also requires the replayed turns
    to start with the user and then alternate, so runs of the same role collapse to
    the latest one — which is what a partial turn left behind by a failed reply
    would otherwise produce.
    """
    if not isinstance(messages, (list, tuple)):
        return []
    turns = []
    for item in list(messages)[-max_turns:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role not in ("user", "model"):
            continue
        content = message(item.get("content"), limit)
        if not content:
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1] = {"role": role, "content": content}
        else:
            turns.append({"role": role, "content": content})

    if turns and turns[0]["role"] == "model":
        turns.pop(0)
    return turns
