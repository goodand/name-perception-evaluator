"""격리 평가자(scripts/review_explanations.py) 명세 — 사용자 2026-11-05 "격리 평가자를 둬".

평가자는 후보·규칙을 만든 쪽과 다른 격리 프로세스. 의도·이웃 개념 이름·설명문만 받고 규칙 신호어·판정은 받지 않는다.
사람 관점(최종 사용자·UX)으로 보고 경고만 낸다. 제외는 규칙 게이트가 한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import review_explanations as rv  # noqa: E402
import run_naming as rn  # noqa: E402
from test_run_naming import BRIEF, PROFILE, fake_factory  # noqa: E402


def fake_reviewer(seen):
    def make(kind, model, art_dir):
        def call(prompt, timeout):
            seen.append(prompt)
            body = prompt.split("설명:\n", 1)[1].splitlines()
            return "\n".join(f"{l.split('.')[0]}. 다른 뜻 — 검사기" if "린터" in l else f"{l.split('.')[0]}. 같음"
                             for l in body)
        return call
    return make


def test_reviewer_flags_and_sees_no_rule_signals(tmp_path):
    seen = []
    out = rn.run(PROFILE, BRIEF, ["name-forecast", "name-linter-x"], tmp_path, rounds=1,
                 backend_factory=fake_factory([]), check_network=False, reviewer=("claude", "sonnet"),
                 reviewer_factory=fake_reviewer(seen))
    rev = out["review"]
    assert rev["C01:end_user"]["same"] == 2 and rev["C02:end_user"]["other"][0]["read_as"] == "검사기"
    assert "격리 평가자" in (tmp_path / "report.md").read_text(encoding="utf-8")
    blob = json.dumps(seen, ensure_ascii=False)
    for leak in ("misread", "must", "camelcase", "제외", "통과"):  # 규칙 신호어·판정은 평가자에게 가지 않는다
        assert leak not in blob, leak
    assert all("name-linter-x" not in p for p in seen if "forecast" in p)  # 다른 후보 이름도 안 감


def test_reviewer_uses_human_views(tmp_path):
    seen = []
    out = rn.run(PROFILE, {**BRIEF, "audience": "end-user"}, ["name-forecast"], tmp_path, rounds=1,
                 backend_factory=fake_factory([]), check_network=False, reviewer=("claude", "sonnet"),
                 reviewer_factory=fake_reviewer(seen))
    assert set(out["review"]) == {"C01:ux", "C01:end_user"}
    assert {p.split("\n\n의도")[0] for p in seen} == {rv.INSTR.format(view=v) for v in rv.VIEWS.values()}


def test_reviewer_failure_is_recorded_not_fatal(tmp_path):
    def make(kind, model, art_dir):
        def call(prompt, timeout):
            raise RuntimeError("down")
        return call
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory([]),
                 check_network=False, reviewer=("claude", "sonnet"), reviewer_factory=make)
    assert "down" in out["review"]["C01:end_user"]["error"] and out["selected"] == "name-forecast"
