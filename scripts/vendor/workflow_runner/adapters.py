"""Small, isolated oh-my-pi RPC adapter using the existing Codex OAuth store.

The workflow supplies only explicit payload fields; OMP adds built-in instructions. The
adapter never reads or copies credential files. Its usage budget is a
post-response guard because OMP does not expose a reliable incremental usage
event in this RPC path.
"""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable


_OMP_ROOT = Path(r"D:\web_chat_gpt\harness-evaluation-20261019\omp")
_OMP_EXE = _OMP_ROOT / "omp.exe"
_CONTROLLED_CONFIG = _OMP_ROOT / "controlled.yml"
_PROVIDER = "openai-codex"
_MODEL = "gpt-6-luna"
_THINKING = "medium"
_SYSTEM_PROMPT = (
    "You are an isolated workflow worker. Use only the task and data supplied "
    "in the current user message. Return only the requested result."
)
_SECRET_ENV_SUFFIXES = (
    "_API_KEY",
    "_ACCESS_TOKEN",
    "_AUTH_TOKEN",
    "_OAUTH_TOKEN",
    "_CLIENT_SECRET",
    "_PASSWORD",
)


def _result(
    status: str,
    *,
    output: dict[str, Any] | None = None,
    usage: int | None = None,
    summary: str = "",
    session_id: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "output": output,
        "usage": usage,
        "summary": summary,
        "session_id": session_id,
    }


def _safe_child_env(state_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in tuple(env):
        upper = name.upper()
        if upper.endswith(_SECRET_ENV_SUFFIXES) or re.search(
            r"(^|_)(API_KEY|ACCESS_TOKEN|AUTH_TOKEN|OAUTH_TOKEN|CLIENT_SECRET|PASSWORD)$",
            upper,
        ):
            env.pop(name, None)
    env["PI_CODING_AGENT_DIR"] = str(state_dir)
    env["NODE_USE_SYSTEM_CA"] = "1"
    return env


def _assistant_text(agent_end: dict[str, Any]) -> str:
    messages = agent_end.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            pieces: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                    text = block.get("text")
                    if isinstance(text, str):
                        pieces.append(text)
            return "\n".join(pieces)
    return ""


def _reported_usage(agent_end: dict[str, Any]) -> int | None:
    messages = agent_end.get("messages")
    if not isinstance(messages, list):
        return None
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            return None
        value = usage.get("totalTokens")
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        # Some provider versions expose only input/output counts.
        inputs, outputs = usage.get("input"), usage.get("output")
        if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in (inputs, outputs)):
            return inputs + outputs
        return None
    return None


def _parse_json_output(text: str) -> dict[str, Any] | None:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    try:
        value = json.loads(candidate)
        json.dumps(value,allow_nan=False)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _terminate_owned_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def run_agent(
    payload: dict,
    instruction: str,
    timeout: float,
    token_budget: int | None,
    cancel: Callable[[], bool],
    artifact_dir: Path,
) -> dict:
    """Run one fresh OMP OAuth session and return a structured result.

    ``token_budget`` is checked against the completed response's reported
    usage. It cannot prevent an in-flight request from exceeding the limit.
    ``cancel`` is polled while awaiting RPC events; cancellation terminates
    only the OMP process launched by this call.
    """
    artifact_dir = Path(artifact_dir).resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(payload, dict) or not isinstance(instruction, str):
        return _result("failed", summary="payload must be a dict and instruction must be text")
    if timeout <= 0 or (token_budget is not None and token_budget <= 0):
        return _result("failed", summary="timeout and token_budget must be positive")
    if not _OMP_EXE.is_file() or not _CONTROLLED_CONFIG.is_file():
        return _result("failed", summary="pinned OMP executable or controlled config is missing")

    run_dir = artifact_dir / "omp-run"
    session_dir = run_dir / "sessions"
    work_dir = run_dir / "work"
    state_dir = _OMP_ROOT / "state"  # Reuses existing OAuth state; never opened by this adapter.
    for directory in (session_dir, work_dir):
        directory.mkdir(parents=True, exist_ok=True)

    args = [
        str(_OMP_EXE),
        "--mode", "rpc",
        "--no-ui",
        "--no-tools",
        "--no-extensions",
        "--no-skills",
        "--no-rules",
        "--no-lsp",
        "--no-title",
        "--config", str(_CONTROLLED_CONFIG),
        "--session-dir", str(session_dir),
        "--system-prompt", _SYSTEM_PROMPT,
        "--provider", _PROVIDER,
        "--model", _MODEL,
        "--thinking", _THINKING,
    ]
    try:
        proc = subprocess.Popen(
            args,
            cwd=work_dir,
            env=_safe_child_env(state_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        return _result("failed", summary=f"could not start OMP ({type(exc).__name__})")

    frames: queue.Queue[dict[str, Any] | str | None] = queue.Queue()
    stderr_done = threading.Event()
    stderr_size = [0]

    def read_stdout() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                frame = json.loads(line)
                frames.put(frame if isinstance(frame, dict) else {"_invalid_frame": True})
            except ValueError:
                frames.put("non_json_stdout")
        frames.put(None)

    def drain_stderr() -> None:
        assert proc.stderr is not None
        # Drain without retaining potentially sensitive provider diagnostics.
        for chunk in iter(lambda: proc.stderr.read(4096), ""):
            stderr_size[0] += len(chunk)
        stderr_done.set()

    threading.Thread(target=read_stdout, name="omp-rpc-stdout", daemon=True).start()
    threading.Thread(target=drain_stderr, name="omp-rpc-stderr", daemon=True).start()

    metadata: dict[str, Any] = {
        "provider": _PROVIDER,
        "model": _MODEL,
        "thinking": _THINKING,
        "fresh_process_session": True,
        "tools_disabled": True,
        "context_discovery_disabled": True,
        "raw_context_saved": False,
        "raw_stderr_saved": False,
        "prompt_acknowledged": False,
        "prompt_result_received": False,
        "agent_end_received": False,
        "session_settled": False,
        "stderr_bytes_drained": 0,
        "events": [],
    }
    next_id = 0
    pending: dict[str, dict[str, Any]] = {}
    prompt_id: str | None = None
    agent_end: dict[str, Any] | None = None
    prompt_result: dict[str, Any] | None = None
    session_id: str | None = None
    deadline = time.monotonic() + timeout
    terminal_status: str | None = None
    terminal_summary = ""

    def send(command: str, **fields: Any) -> str:
        nonlocal next_id
        next_id += 1
        ident = f"workflow-{next_id}"
        assert proc.stdin is not None
        proc.stdin.write(json.dumps({"id": ident, "type": command, **fields}, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        pending[ident] = {"command": command}
        return ident

    def record_event(frame: dict[str, Any]) -> None:
        event_type = frame.get("type", "unknown")
        metadata["events"].append(event_type)
        if event_type == "agent_start":
            metadata["agent_started"] = True
        elif event_type == "agent_end" and frame.get("isTerminal") is not False:
            nonlocal agent_end
            agent_end = frame
            metadata["agent_end_received"] = True
            metadata["terminal_agent_end"] = True
        elif event_type == "prompt_result" and frame.get("id") == prompt_id:
            nonlocal prompt_result
            prompt_result = frame
            metadata["prompt_result_received"] = True
            metadata["prompt_status"] = frame.get("status")
            if frame.get("sessionSettled") is True:
                metadata["session_settled"] = True
        elif event_type == "session_settled":
            metadata["session_settled"] = True

    def wait_until(predicate: Callable[[], bool]) -> bool:
        while time.monotonic() < deadline:
            if cancel():
                return False
            if proc.poll() is not None and frames.empty():
                return False
            try:
                frame = frames.get(timeout=min(0.1, max(0.01, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if frame is None:
                return False
            if isinstance(frame, str):
                metadata["non_json_stdout_frames"] = metadata.get("non_json_stdout_frames", 0) + 1
                continue
            record_event(frame)
            if frame.get("type") == "response":
                ident = frame.get("id")
                if ident in pending:
                    pending[ident]["response"] = frame
                    if ident == prompt_id and frame.get("success"):
                        metadata["prompt_acknowledged"] = True
                        data = frame.get("data")
                        if isinstance(data, dict) and "agentInvoked" in data:
                            metadata["prompt_agent_invoked"] = data.get("agentInvoked")
            if predicate():
                return True
        return False

    try:
        if not wait_until(lambda: any("ready" in metadata["events"] for _ in (0,))):
            terminal_status = "cancelled" if cancel() else "timed_out" if time.monotonic() >= deadline else "failed"
            terminal_summary = "OMP RPC did not become ready"
        else:
            # Lock protocol/model settings and disable retry/cache warming.
            setup_ids = [
                send("set_auto_retry", enabled=False),
                send("set_cache_warming", mode="off"),
                send("set_model", provider=_PROVIDER, modelId=_MODEL),
                send("set_thinking_level", level=_THINKING),
                send("get_state"),
            ]
            if not wait_until(lambda: all("response" in pending[i] for i in setup_ids)):
                terminal_status = "cancelled" if cancel() else "timed_out" if time.monotonic() >= deadline else "failed"
                terminal_summary = "OMP setup did not complete"
            elif any(not pending[i]["response"].get("success") for i in setup_ids):
                terminal_status = "failed"
                terminal_summary = "OMP rejected isolation or model configuration"
            else:
                state = pending[setup_ids[-1]]["response"].get("data", {})
                session_id = state.get("sessionId") if isinstance(state, dict) else None
                model = state.get("model", {}) if isinstance(state, dict) else {}
                metadata["selected_provider"] = model.get("provider") if isinstance(model, dict) else None
                metadata["selected_model"] = model.get("id") if isinstance(model, dict) else None
                metadata["session_id_observed"] = bool(session_id)
                if not session_id or state.get('messageCount')!=0 or state.get('dumpTools')!=[] or model.get('provider')!=_PROVIDER or model.get('id')!=_MODEL or state.get('thinkingLevel')!=_THINKING:
                    raise ValueError('Observed worker state violates contract')
                import hashlib
                metadata['observed_system_prompt_hash']=hashlib.sha256(json.dumps(state.get('systemPrompt'),sort_keys=True).encode()).hexdigest()
                metadata['wire_payload_observed']=False
                metadata['os_isolation_verified']=False
                metadata['session_settled']=False
                task = (
                    instruction
                    + "\n\nINPUT DATA (JSON):\n"
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                )
                prompt_id = send("prompt", message=task)
                if not wait_until(
                    lambda: (
                        prompt_result is not None
                        and prompt_result.get("id") == prompt_id
                        and metadata["session_settled"]
                        and (prompt_result.get('status')!='completed' or agent_end is not None)
                    )
                ):
                    if cancel():
                        terminal_status = "cancelled"
                        terminal_summary = "workflow cancellation requested; owned OMP process was terminated"
                    elif time.monotonic() >= deadline:
                        terminal_status = "timed_out"
                        terminal_summary = "deadline reached; owned OMP process was terminated"
                    else:
                        terminal_status = "failed"
                        terminal_summary = "OMP exited before prompt_result and session_settled"
                elif prompt_result.get("status") != "completed":
                    terminal_status = "failed"
                    terminal_summary = "OMP prompt did not complete successfully"
                elif agent_end is None:
                    terminal_status = "failed"
                    terminal_summary = "completed prompt had no terminal agent_end frame"
                else:
                    usage = _reported_usage(agent_end)
                    text = _assistant_text(agent_end)
                    output = _parse_json_output(text)
                    if usage is None:
                        terminal_status = "failed"
                        terminal_summary = "completed response did not report valid token usage"
                    elif output is None:
                        terminal_status = "failed"
                        terminal_summary = "assistant response was not a JSON object"
                    elif token_budget is not None and usage > token_budget:
                        terminal_status = "budget_exceeded"
                        terminal_summary = "reported usage exceeded the post-response budget; this is not a hard cap"
                    else:
                        terminal_status = "succeeded"
                        terminal_summary = "prompt_result and session_settled received"

    except (BrokenPipeError, OSError, ValueError, TypeError) as exc:
        terminal_status = "failed"
        terminal_summary = f"OMP RPC failure ({type(exc).__name__})"
    finally:
        if terminal_status in ("cancelled", "timed_out"):
            try:
                if proc.poll() is None and proc.stdin is not None:
                    proc.stdin.write(json.dumps({"id": "workflow-abort", "type": "abort"}) + "\n")
                    proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError):
                pass
            _terminate_owned_process(proc)
        elif proc.poll() is None:
            try:
                assert proc.stdin is not None
                proc.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _terminate_owned_process(proc)
        metadata["stderr_bytes_drained"] = stderr_size[0]
        metadata["process_exit_code"] = proc.poll()
        metadata_path = artifact_dir / "omp-metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    usage = _reported_usage(agent_end) if agent_end is not None else None
    output = _parse_json_output(_assistant_text(agent_end)) if agent_end is not None else None
    return _result(
        terminal_status or "failed",
        output=output if terminal_status in ("succeeded", "budget_exceeded") else None,
        usage=usage,
        summary=terminal_summary,
        session_id=session_id,
    )


def normalize_codexctl(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Normalize a codexctl snapshot's status/usage without claiming equivalence.

    codexctl reports interrupted phase separately from the top-level status;
    preserve both so a comparison does not mistake a completed CLI wait for a
    completed model turn.
    """
    usage = snapshot.get("usage")
    if isinstance(usage, dict):
        value = usage.get("totalTokens", usage.get("total_tokens"))
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            value = None
    else:
        value = usage if isinstance(usage, int) and not isinstance(usage, bool) and usage >= 0 else None
    phase = snapshot.get("current_phase", snapshot.get("phase"))
    status = snapshot.get("status")
    if phase == "interrupted" or status == "interrupted":
        normalized = "cancelled"
    elif status in ("completed", "succeeded"):
        normalized = "succeeded"
    elif status in ("timed_out", "timeout"):
        normalized = "timed_out"
    elif status in ("failed", "error"):
        normalized = "failed"
    else:
        normalized = "unknown"
    return {
        "status": normalized,
        "reported_status": status,
        "reported_phase": phase,
        "usage": value,
        "session_id": snapshot.get("session_id", snapshot.get("thread_id")),
    }
