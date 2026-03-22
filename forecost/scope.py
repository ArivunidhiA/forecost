"""Heuristic and optional LLM-powered project scope analyzer for baseline estimates."""

import json
import re
from pathlib import Path

from forecost.pricing import calculate_cost

__all__ = ["analyze_heuristic", "analyze_with_llm"]

_PROJECT_KEYWORDS = ("chatbot", "agent", "rag", "retrieval", "assistant")
_SDK_PATTERNS = [
    (r"import\s+openai\b", "openai"),
    (r"from\s+openai\b", "openai"),
    (r"import\s+anthropic\b", "anthropic"),
    (r"from\s+anthropic\b", "anthropic"),
    (r"require\(['\"]openai['\"]\)", "openai"),
    (r"from\s+['\"]openai['\"]", "openai"),
    (r"require\(['\"]@anthropic-ai/sdk['\"]\)", "anthropic"),
    (r"from\s+['\"]@anthropic-ai/sdk['\"]", "anthropic"),
]
_README_NAMES = ("README.md", "readme.md", "Readme.md", "spec.md", "CLAUDE.md", ".cursorrules")


def _count_files_by_extension(project_path: str) -> dict[str, int]:
    ext_counts: dict[str, int] = {}
    root = Path(project_path)
    if not root.is_dir():
        return ext_counts
    for p in root.rglob("*"):
        if p.is_symlink() or not p.is_file() or _is_ignored(p, root):
            continue
        ext = p.suffix or "(no ext)"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    manifests = ("package.json", "go.mod", "Cargo.toml", "tsconfig.json", "pom.xml")
    for manifest in manifests:
        if (root / manifest).is_file():
            ext_counts[manifest] = ext_counts.get(manifest, 0) + 1
    return ext_counts


_MAX_SCAN_DEPTH = 6


def _is_ignored(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) > _MAX_SCAN_DEPTH:
        return True
    if ".git" in parts or "__pycache__" in parts or "node_modules" in parts:
        return True
    if "vendor" in parts or ".venv" in parts or "venv" in parts:
        return True
    if any(p.startswith(".") for p in parts):
        return True
    return False


def _read_readme_snippet(project_path: str, max_chars: int = 2000) -> str:
    root = Path(project_path)
    for name in _README_NAMES:
        p = root / name
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8", errors="replace")[:max_chars]
            except OSError:
                pass
    return ""


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


def _detect_sdk_imports(project_path: str) -> set[str]:
    found: set[str] = set()
    root = Path(project_path)
    files: list[Path] = []
    for ext in ("*.py", "*.js", "*.ts", "*.tsx", "*.jsx"):
        files.extend(list(root.rglob(ext))[:50])
    files = files[:100]
    for p in files:
        if p.is_symlink() or not p.is_file() or _is_ignored(p, root):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:50]
            content = "\n".join(lines)
            for pattern, sdk in _SDK_PATTERNS:
                if re.search(pattern, content):
                    found.add(sdk)
        except OSError:
            pass
    return found


def analyze_heuristic(project_path: str) -> dict:
    ext_counts = _count_files_by_extension(project_path)
    total_files = sum(ext_counts.values())

    readme = _read_readme_snippet(project_path)
    has_agent_kw = _has_keyword(readme, _PROJECT_KEYWORDS)
    has_rag_kw = _has_keyword(readme, ("rag", "retrieval"))

    sdks = _detect_sdk_imports(project_path)
    use_anthropic = "anthropic" in sdks

    if total_files < 10:
        estimated_days = 7
    elif total_files <= 50:
        estimated_days = 14
    elif total_files <= 200:
        estimated_days = 21
    else:
        estimated_days = 30

    if has_agent_kw and not has_rag_kw:
        project_type = "agent"
        calls_per_day = 80
        tokens_in, tokens_out = 2000, 1500
        model = "claude-3-5-sonnet-latest" if use_anthropic else "gpt-4o"
        daily_cost = calls_per_day * calculate_cost(model, tokens_in, tokens_out)
    elif has_rag_kw or has_agent_kw:
        project_type = "rag"
        embed_calls, embed_model, embed_tokens = 100, "text-embedding-3-small", 1500
        gen_calls = 25
        gen_model = "claude-3-5-sonnet-latest" if use_anthropic else "gpt-4o"
        gen_tokens_in, gen_tokens_out = 3000, 1000
        model = gen_model
        tokens_in, tokens_out = gen_tokens_in, gen_tokens_out
        calls_per_day = embed_calls + gen_calls
        daily_cost = embed_calls * calculate_cost(
            embed_model, embed_tokens, 0
        ) + gen_calls * calculate_cost(gen_model, gen_tokens_in, gen_tokens_out)
    else:
        project_type = "default"
        calls_per_day = 50
        tokens_in, tokens_out = 600, 1000
        model = "claude-3-5-haiku-latest" if use_anthropic else "gpt-4o-mini"
        daily_cost = calls_per_day * calculate_cost(model, tokens_in, tokens_out)

    total_cost = daily_cost * estimated_days

    return {
        "estimated_days": estimated_days,
        "daily_cost": round(daily_cost, 6),
        "total_cost": round(total_cost, 6),
        "confidence": "low",
        "source": "heuristic",
        "project_type": project_type,
        "model": model,
        "calls_per_day": calls_per_day,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
    }


def _gather_llm_context(project_path: str) -> str:
    root = Path(project_path)
    parts: list[str] = []

    for name in _README_NAMES:
        p = root / name
        if p.is_file():
            try:
                parts.append(
                    f"--- {p.name} ---\n{p.read_text(encoding='utf-8', errors='replace')[:3000]}"
                )
            except OSError:
                pass
            break

    for name in (".cursorrules", "CLAUDE.md", ".github/copilot-instructions.md"):
        p = root / name
        if p.is_file():
            try:
                parts.append(
                    f"--- {name} ---\n{p.read_text(encoding='utf-8', errors='replace')[:2000]}"
                )
            except OSError:
                pass

    code_files: list[Path] = []
    for ext in ("*.py", "*.js", "*.ts", "*.tsx"):
        code_files.extend(sorted(root.rglob(ext))[:25])
    code_files = code_files[:50]
    for p in code_files:
        if not p.is_file() or _is_ignored(p, root):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:30]
            parts.append(f"--- {p.relative_to(root)} ---\n" + "\n".join(lines))
        except OSError:
            pass

    return "\n\n".join(parts)


def analyze_with_llm(project_path: str, api_key: str | None = None) -> dict:
    try:
        import litellm
    except ImportError:
        return analyze_heuristic(project_path)

    context = _gather_llm_context(project_path)
    if not context.strip():
        return analyze_heuristic(project_path)

    prompt = f"""Analyze this project and return a JSON object \
with exactly these keys (no other text):
- project_type: one of "agent", "rag", "default"
- calls_per_day: integer estimate
- tokens_in: integer per-call input tokens
- tokens_out: integer per-call output tokens
- model: "gpt-4o-mini" or "claude-3-5-haiku-latest"
- estimated_days: integer (7, 14, or 30)

Project content:
{context[:12000]}
"""

    try:
        kwargs: dict = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]}
        if api_key:
            kwargs["api_key"] = api_key

        resp = litellm.completion(**kwargs)
        content = resp.choices[0].message.content
        if not content:
            return analyze_heuristic(project_path)

        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```\w*\n?", "", content)
            content = re.sub(r"\n?```\s*$", "", content)
        parsed = json.loads(content)

        project_type = str(parsed.get("project_type", "default"))
        calls_per_day = int(parsed.get("calls_per_day", 50))
        tokens_in = int(parsed.get("tokens_in", 600))
        tokens_out = int(parsed.get("tokens_out", 1000))
        model = str(parsed.get("model", "gpt-4o-mini"))
        estimated_days = int(parsed.get("estimated_days", 14))

        cost_per_call = calculate_cost(model, tokens_in, tokens_out)
        daily_cost = calls_per_day * cost_per_call
        total_cost = daily_cost * estimated_days

        return {
            "estimated_days": estimated_days,
            "daily_cost": round(daily_cost, 6),
            "total_cost": round(total_cost, 6),
            "confidence": "medium",
            "source": "llm",
            "project_type": project_type,
            "model": model,
            "calls_per_day": calls_per_day,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        }
    except Exception:
        return analyze_heuristic(project_path)
