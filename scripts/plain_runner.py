"""평문 답변자: 지시문과 이름을 평문으로 주고 평문 답을 그대로 받는다(입출력 형식 신호를 넣지 않음).

동봉 실행기(vendor/workflow_runner)는 입력을 형식화된 데이터로 감싸고 "workflow worker" 시스템 프롬프트를 쓴다.
둘 다 답변을 한쪽으로 끌 수 있는 신호라, claude·로컬 LLM은 이 모듈로 부른다. claude 실행 옵션(격리)은
vendor/workflow_runner/claude_adapter.py와 같고 시스템 프롬프트만 다르다. 동봉 실행기는 고치지 않는다.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = "주어진 요청에만 답하세요."
LMS_CHAT = "http://127.0.0.1:1234/v1/chat/completions"


def _clean(text: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    return re.sub(r"^\s*(뜻|설명)\s*[:：]\s*", "", text)


def claude_text(prompt: str, model: str, timeout: float, art_dir: Path | None = None) -> str:
    from collect_samples import RUNNER

    sys.path.insert(0, str(RUNNER))
    from adapters import _safe_child_env

    args = [shutil.which("claude") or "claude", "-p", "--setting-sources", "", "--tools", "",
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--system-prompt", SYSTEM_PROMPT, "--exclude-dynamic-system-prompt-sections",
            "--disable-slash-commands", "--no-session-persistence", "--model", model, "--output-format", "json"]
    with tempfile.TemporaryDirectory(prefix="iso_") as work:
        cp = subprocess.run(args, input=prompt, cwd=work, env=_safe_child_env(Path(work)), capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    d = json.loads(cp.stdout)  # 실행기 출력 봉투(답변 내용은 평문)
    if art_dir:
        Path(art_dir).mkdir(parents=True, exist_ok=True)
        (Path(art_dir) / "claude-metadata.json").write_text(
            json.dumps({k: d.get(k) for k in ("session_id", "modelUsage", "usage", "total_cost_usd")},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    if d.get("is_error"):
        raise RuntimeError(f"claude 오류: {str(d.get('result', ''))[:200]}")
    return _clean(d.get("result", ""))


def qwen_text(prompt: str, model: str, timeout: float, art_dir: Path | None = None) -> str:
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7}
    req = urllib.request.Request(LMS_CHAT, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    return _clean(json.load(urllib.request.urlopen(req, timeout=timeout))["choices"][0]["message"]["content"])


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
