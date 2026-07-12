"""Rule-based task-category classifier — 12 categories (round3-estimation §2.3).

Deliberately simple (ordered regex rules): cheap, explainable, testable. The
LLM is never used to estimate a number (banned — 0.39 self-prediction ceiling);
this classifier is the one place a future LLM-assist could sit (v2), and even
then it would only pick a category label, never a cost/time/success number.
"""

from __future__ import annotations

import re

_RULES: list[tuple[str, re.Pattern]] = [
    ("fanout-batch", re.compile(r"\b(parallel|subagents?|swarm|spawn|fan[- ]?out)\b", re.I)),
    ("test-work", re.compile(r"\b(tests?|testing|pytest|specs?|coverage)\b", re.I)),
    ("bugfix-debug", re.compile(r"\b(fix|bug|debug|issue|broken|crash|error)\b", re.I)),
    ("refactor", re.compile(r"\b(refactor|restructure|clean ?up|simplify)\b", re.I)),
    ("docs-writing", re.compile(r"\b(docs?|documentation|readme|comment)\b", re.I)),
    ("config-devops", re.compile(r"\b(ci|cd|deploy|docker|config|pipeline|build)\b", re.I)),
    ("repo-research", re.compile(r"\b(explain|find|review|understand|what does)\b", re.I)),
    ("web-research", re.compile(r"\b(research|search the web|look up)\b", re.I)),
    ("data-scripting", re.compile(r"\b(script|analyze|extract|parse|csv|dataset)\b", re.I)),
    ("continuation-misc", re.compile(r"^/|^\s*(yes|ok|continue|thanks)\s*$", re.I)),
]

SCOPE_MAXIMIZER_RE = re.compile(
    r"\b(all|every|entire|comprehensive|throughout|across the codebase)\b", re.IGNORECASE
)
SENSITIVE_PATH_RE = re.compile(
    r"(auth|session|migrat|payment|billing|\.env|secret|credential|ci\.ya?ml|"
    r"\.github/workflows)",
    re.IGNORECASE,
)


def classify(prompt: str) -> str:
    for label, pattern in _RULES:
        if pattern.search(prompt):
            return label
    if re.search(r"\b(add|implement|build|create|write)\b", prompt, re.I):
        return "feature-build"
    return "quick-edit"
