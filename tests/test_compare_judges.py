"""판정기 기존안 비교(scripts/compare_judges.py) 명세 — 수정 프로토콜 '기존안과 후보를 같은 입력으로 비교'.

판정기를 고칠 때: 기존안(git 커밋의 check_terms.py)과 새 판정기를 같은 (규칙, 표본) 쌍에 돌려
이름별 판정 줄을 비교한다. 줄바꿈(CR) 차이는 무시하고, 새 쪽에만 있는 '선택:' 같은 덧붙은 줄은 따로 센다.
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import compare_judges as cj  # noqa: E402

RULE = {"id": "R01", "term": "merge-desk", "must": [["표"], ["결정"]], "must_not": []}


def _pair(tmp_path):
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_terms as ct
    r = tmp_path / "r.json"
    r.write_text(json.dumps({"terms": [RULE]}, ensure_ascii=False), encoding="utf-8")
    s = tmp_path / "s.jsonl"
    env = {"format": "samples/v2", "role": "target", "status": "ok", "backend": "fake",
           "items": [{"id": "R01", "term": "merge-desk", "explanation": "표를 결정"}],
           "rule_hashes": {"R01": ct.rule_hash(RULE)}}
    s.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return r, [s]


def test_same_judge_no_diff(tmp_path):
    r, s = _pair(tmp_path)
    old = tmp_path / "old_check_terms.py"
    shutil.copy(ROOT / "scripts/check_terms.py", old)
    out = cj.compare(old, ROOT / "scripts/check_terms.py", [(r, s)])
    assert out["total_lines"] == 1 and out["diff_lines"] == 0


def test_changed_judge_detected(tmp_path):
    r, s = _pair(tmp_path)
    old = tmp_path / "old_check_terms.py"
    src = (ROOT / "scripts/check_terms.py").read_text(encoding="utf-8")
    old.write_text(src.replace('s["pass"] += ok', 's["pass"] += 0'), encoding="utf-8")  # 일부러 틀린 기존안
    out = cj.compare(old, ROOT / "scripts/check_terms.py", [(r, s)])
    assert out["diff_lines"] == 1 and out["pairs"][0]["diff"]


def test_old_from_git_ref():
    """기존안을 git 커밋에서 꺼낸다(f60ed11 = 하네스 v2.1). 그 커밋은 원본(ldx_workbench)에만 있어 분리 저장소에서는 건너뛴다."""
    import pytest, subprocess
    if subprocess.run(["git", "cat-file", "-e", "f60ed11^{commit}"], capture_output=True).returncode != 0:
        pytest.skip("원본 저장소 커밋 f60ed11 없음(분리 저장소)")
    p = cj.old_judge_from_git("f60ed11")
    assert p.is_file() and "JUDGE_VERSION" in p.read_text(encoding="utf-8")
