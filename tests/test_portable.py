"""clone한 다른 PC에서 바로 쓰기 위한 명세 (사용자 2026-11-04: "상대경로로 바꾸거나 세팅하게끔 sh file").

- 답변자 실행기(workflow-runner)는 환경 변수 NAME_HARNESS_RUNNER가 있으면 그 경로, 없으면 저장소 안 동봉본.
- 동봉본은 원본을 수정 없이 복사한 것(PROVENANCE의 sha256과 일치).
"""
import hashlib
import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
VENDOR = ROOT / "scripts/vendor/workflow_runner"


def _reload(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("NAME_HARNESS_RUNNER", raising=False)
    else:
        monkeypatch.setenv("NAME_HARNESS_RUNNER", value)
    import collect_samples
    return importlib.reload(collect_samples)


def test_runner_default_is_vendored(monkeypatch):
    cs = _reload(monkeypatch, None)
    assert Path(cs.RUNNER).resolve() == VENDOR.resolve()
    assert (Path(cs.RUNNER) / "claude_adapter.py").is_file() and (Path(cs.RUNNER) / "adapters.py").is_file()


def test_runner_env_override(monkeypatch, tmp_path):
    cs = _reload(monkeypatch, str(tmp_path))
    assert Path(cs.RUNNER) == tmp_path
    _reload(monkeypatch, None)


def test_vendored_files_match_provenance():
    prov = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert prov["files"]
    for name, meta in prov["files"].items():
        assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == meta["sha256"], name


def test_vendored_matches_original_when_present():
    """원본 workflow-runner가 있는 PC에서만: 원본이 바뀌어 복사본과 어긋나면 실패(다시 복사하고 PROVENANCE 갱신)."""
    import pytest
    prov = json.loads((VENDOR / "PROVENANCE.json").read_text(encoding="utf-8"))
    checked = 0
    for name, meta in prov["files"].items():
        src = Path(meta["source"])
        if not src.is_file():
            continue
        checked += 1
        assert hashlib.sha256(src.read_bytes()).hexdigest() == meta["sha256"], f"원본 {src}가 바뀜: 동봉본 갱신 필요"
    if not checked:
        pytest.skip("원본 workflow-runner가 없는 PC")


def test_vendored_claude_adapter_imports_without_network():
    """동봉본만으로 claude 백엔드를 만들 수 있다(호출은 하지 않음)."""
    code = ("import sys; sys.path.insert(0, r'%s'); import claude_adapter, adapters; "
            "print(callable(claude_adapter.run_agent), callable(adapters.run_agent))" % VENDOR)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).stdout.strip()
    assert out == "True True"


def test_profile_and_brief_example():
    """사용자 기준(주제 무관)은 프로필, 주제별 내용은 브리프로 분리."""
    prof = json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8"))
    for k in ("style", "max_keywords", "collision", "generator", "answerers", "perspectives", "gate", "fallback"):
        assert k in prof, k
    assert prof["max_keywords"] == 3
    brief = json.loads((ROOT / "docs/harness/briefs/name-harness.json").read_text(encoding="utf-8"))
    for k in ("purpose", "human_actions", "distinct_from", "audience"):
        assert k in brief, k
    assert 1 <= len(brief["human_actions"]) <= 3
