"""평문 답변자: 지시문과 이름을 평문으로 주고 평문 답을 그대로 받는다(입출력 형식 신호를 넣지 않음).

동봉 실행기(vendor/workflow_runner)는 입력을 형식화된 데이터로 감싸고 "workflow worker" 시스템 프롬프트를 쓴다.
둘 다 답변을 한쪽으로 끌 수 있는 신호라, claude·로컬 LLM은 이 모듈로 부른다. claude 실행 옵션(격리)은
vendor/workflow_runner/claude_adapter.py와 같고 시스템 프롬프트만 다르다. 동봉 실행기는 고치지 않는다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = "주어진 요청에만 답하세요."
LMS_BASE = os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234").rstrip("/")  # LM Studio 주소는 여기 한 곳
LMS_CHAT = f"{LMS_BASE}/v1/chat/completions"


# ---- 호출 기록: 주체·모델·시간·토큰·비용을 한 줄씩 쌓는다(덮어쓰지 않음, 사용자 2026-11-06) ----
import contextlib  # noqa: E402
import contextvars  # noqa: E402
import time  # noqa: E402

USAGE_LOG = contextvars.ContextVar("usage_log", default=os.environ.get("NAME_HARNESS_USAGE_LOG") or None)
ACTOR = contextvars.ContextVar("actor", default="미지정")


@contextlib.contextmanager
def usage(log=None, actor=None):
    """with usage(<out>/usage.jsonl, "첫눈 독자"): 안에서 일어난 모든 호출을 그 파일에 그 주체로 기록한다."""
    toks = [USAGE_LOG.set(str(log))] if log else []
    atok = ACTOR.set(actor) if actor else None
    try:
        yield
    finally:
        if atok:
            ACTOR.reset(atok)
        for t in toks:
            USAGE_LOG.reset(t)


def record(kind: str, model: str, seconds: float, d: dict | None = None, ok: bool = True) -> None:
    path = USAGE_LOG.get()
    if not path:
        return
    d = d or {}
    u = d.get("usage") or {}
    row = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "actor": ACTOR.get(), "kind": kind, "model": model,
           "seconds": round(seconds, 2), "api_seconds": round((d.get("duration_api_ms") or 0) / 1000, 2) or None,
           "input": u.get("input_tokens", u.get("prompt_tokens")), "output": u.get("output_tokens", u.get("completion_tokens")),
           "cache_read": u.get("cache_read_input_tokens"), "cache_write": u.get("cache_creation_input_tokens"),
           "cost_usd": d.get("total_cost_usd"), "ok": ok}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def summarize(path) -> dict:
    """usage.jsonl → {주체: {calls, seconds, input, output, cache_read, cost_usd}}"""
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        s = out.setdefault(r["actor"], {"calls": 0, "seconds": 0.0, "input": 0, "output": 0, "cache_read": 0, "cost_usd": 0.0})
        s["calls"] += 1
        s["seconds"] = round(s["seconds"] + (r["seconds"] or 0), 2)
        for k in ("input", "output", "cache_read"):
            s[k] += r.get(k) or 0
        s["cost_usd"] = round(s["cost_usd"] + (r.get("cost_usd") or 0), 4)
    return out


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return re.sub(r"^\s*(뜻|설명)\s*[:：]\s*", "", text)


def claude_text(prompt: str, model: str, timeout: float, art_dir: Path | None = None, tools: str = "",
                schema: dict | None = None):
    """tools: 허용할 도구(예: 검색자는 "WebSearch,WebFetch"). 기본은 도구 없음.
    schema: 구조화된 출력(claude --json-schema). 주면 dict를 돌려준다. 응답자·작명자에게는 쓰지 않는다(형식 신호)."""
    from collect_samples import load_adapters

    _safe_child_env = load_adapters()._safe_child_env

    args = [shutil.which("claude") or "claude", "-p", "--setting-sources", "", "--tools", tools, *(["--allowedTools", tools] if tools else []),
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--system-prompt", SYSTEM_PROMPT, "--exclude-dynamic-system-prompt-sections",
            "--disable-slash-commands", "--no-session-persistence", "--model", model, "--output-format", "json",
            *(["--json-schema", json.dumps(schema, ensure_ascii=False)] if schema else [])]
    t0 = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="iso_") as work:
            cp = subprocess.run(args, input=prompt, cwd=work, env=_safe_child_env(Path(work)), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
        d = json.loads(cp.stdout)  # 실행기 출력 봉투(답변 내용은 평문)
    except Exception:
        record("claude", model, time.perf_counter() - t0, ok=False)
        raise
    record("claude", model, time.perf_counter() - t0, d, not d.get("is_error"))
    if art_dir:
        Path(art_dir).mkdir(parents=True, exist_ok=True)
        (Path(art_dir) / "claude-metadata.json").write_text(
            json.dumps({k: d.get(k) for k in ("session_id", "modelUsage", "usage", "total_cost_usd")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    if d.get("is_error"):
        raise RuntimeError(f"claude 오류: {str(d.get('result', ''))[:200]}")
    if schema:
        return d.get("structured_output") or json.loads(d.get("result") or "{}")
    return _clean(d.get("result", ""))


def qwen_text(prompt: str, model: str, timeout: float, art_dir: Path | None = None, schema: dict | None = None):
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    if schema:  # LM Studio 구조화된 출력
        body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema}}
    req = urllib.request.Request(LMS_CHAT, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception:
        record("qwen", model, time.perf_counter() - t0, ok=False)
        raise
    record("qwen", model, time.perf_counter() - t0, {"usage": d.get("usage")})
    text = d["choices"][0]["message"]["content"]
    return json.loads(_clean(text)) if schema else _clean(text)


TEXT = {"claude": claude_text, "qwen": qwen_text}


def ask_name(text_fn, instr: str, term: str) -> str:
    """답변자 평문 프롬프트: 지시문 + 빈 줄 + '이름: …'."""
    return f"{instr}\n\n이름: {term}"


def make_backend(kind: str, model: str, art_dir: Path, instr_ref):
    """collect_samples.collect가 부르는 call(names, timeout). 이름 하나씩(solo)만. instr_ref()는 부를 때의 지시문."""
    text_fn = TEXT[kind]

    def call(names, timeout):
        if len(names) != 1:
            raise ValueError("평문 답변자는 이름 하나씩만 받는다(solo)")
        n = names[0]
        return {"items": [{"id": n["id"], "term": n["term"],
                           "explanation": text_fn(ask_name(text_fn, instr_ref(), n["term"]), model, timeout, art_dir)}]}
    return call
