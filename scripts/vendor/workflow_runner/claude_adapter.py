"""Context-isolated Claude call via ``claude -p``; same return shape as adapters.run_agent.

Isolation: no setting sources (CLAUDE.md/memory/skills/hooks off), no tools, no MCP,
fixed system prompt, empty neutral cwd, no session persistence. Auth = the logged-in
the already logged-in subscription account of the CLI (no API key handled here).
Known residue: Claude Code still injects userEmail and an env block (cwd, OS, date, model).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from adapters import _parse_json_output, _result, _safe_child_env, _SYSTEM_PROMPT

_MODEL = "claude-opus-5-5"


def run_agent(payload: dict, instruction: str, timeout: float, token_budget: int | None,
              cancel: Callable[[], bool], artifact_dir: Path, model: str = _MODEL) -> dict:
    artifact_dir = Path(artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, dict) or not isinstance(instruction, str):
        return _result("failed", summary="payload must be a dict and instruction must be text")
    if timeout <= 0 or (token_budget is not None and token_budget <= 0):
        return _result("failed", summary="timeout and token_budget must be positive")
    prompt = instruction + "\n\n" + json.dumps(payload, ensure_ascii=False)
    args = [shutil.which("claude") or "claude", "-p", "--setting-sources", "", "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--system-prompt", _SYSTEM_PROMPT, "--exclude-dynamic-system-prompt-sections",
            "--disable-slash-commands", "--no-session-persistence",
            "--model", model, "--output-format", "json"]
    if cancel():
        return _result("cancelled", summary="cancelled before start")
    try:
        with tempfile.TemporaryDirectory(prefix="iso_") as work:
            cp = subprocess.run(args, input=prompt, cwd=work, env=_safe_child_env(Path(work)), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return _result("timed_out", summary="claude -p timed out")
    except OSError as exc:
        return _result("failed", summary=f"could not start claude ({type(exc).__name__})")
    try:
        d = json.loads(cp.stdout)
    except ValueError:
        return _result("failed", summary=f"claude exit {cp.returncode}, unparsable output")
    u = d.get("usage") or {}
    usage = sum(u.get(k, 0) for k in ("input_tokens", "output_tokens",
                                       "cache_creation_input_tokens", "cache_read_input_tokens"))
    (artifact_dir / "claude-metadata.json").write_text(
        json.dumps({k: d.get(k) for k in ("session_id", "modelUsage", "usage", "total_cost_usd")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    if d.get("is_error"):
        return _result("failed", usage=usage, summary="claude reported error", session_id=d.get("session_id"))
    status = "budget_exceeded" if token_budget and usage > token_budget else "succeeded"
    return _result(status, output=_parse_json_output(d.get("result", "")), usage=usage,
                   session_id=d.get("session_id"))
