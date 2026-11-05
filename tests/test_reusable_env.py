"""다른 PC 재사용: PC 고정 경로를 환경 변수로 덮어쓴다(CLEANUP_PLAN 3절, 사용자 2026-11-05 "재사용성 남은 항목 고쳐").

- NAME_HARNESS_OMP_ROOT: 동봉 실행기(adapters)의 gpt OMP 경로를 import 뒤 덮어쓴다(동봉본 무수정).
- LMSTUDIO_URL: LM Studio 주소 한 곳(plain_runner.LMS_BASE)에서 namecheck·ask_local_llm이 가져다 쓴다.
- ldx 전용 기본 입력 경로는 없앴다: 인자 없이 부르면 안내 메시지로 끝난다.
"""
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_samples as cs  # noqa: E402


def test_omp_root_env_overrides_adapters(monkeypatch, tmp_path):
    monkeypatch.setenv("NAME_HARNESS_OMP_ROOT", str(tmp_path))
    ad = cs.load_adapters()
    assert Path(ad._OMP_ROOT) == tmp_path and ad._OMP_EXE.parent == tmp_path and ad._CONTROLLED_CONFIG.name == "controlled.yml"
    # 동봉 원문은 그대로(sha256은 test_portable이 본다): 덮어쓰기는 메모리에서만
    assert "NAME_HARNESS_OMP_ROOT" not in (cs.RUNNER / "adapters.py").read_text(encoding="utf-8")


def test_lmstudio_url_env_single_source(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_URL", "http://10.0.0.5:5555/")
    import plain_runner
    importlib.reload(plain_runner)
    assert plain_runner.LMS_CHAT == "http://10.0.0.5:5555/v1/chat/completions"
    import namecheck
    importlib.reload(namecheck)
    assert namecheck.LMS_URL == "http://10.0.0.5:5555/v1/models"
    monkeypatch.delenv("LMSTUDIO_URL")
    importlib.reload(plain_runner)
    importlib.reload(namecheck)


def test_no_ldx_default_paths():
    for script, msg in (("check_terms.py", "규칙 파일"), ("ask_local_llm.py", "용어 파일")):
        cp = subprocess.run([sys.executable, str(ROOT / "scripts" / script)] + (["x", "1", "o.json"] if "ask" in script else []),
                            capture_output=True, text=True, encoding="utf-8",
                            env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
        assert cp.returncode != 0 and msg in (cp.stderr + cp.stdout), script
    for f in ("check_terms.py", "ask_local_llm.py"):
        assert "docs/glossary" not in (ROOT / "scripts" / f).read_text(encoding="utf-8").split('"""', 2)[2]
