"""명명 실패 사례 데이터셋 회귀 (docs/harness/naming_failures.json).

출처: 이름 검증 세션 issue case(2026-11-04, 커밋 fd9aca1·67c061b) + 명명 전담 세션 실측(s12~s14, reexp).
조각 단어로 잡히는 오독 사례는 위험 단어 사전(risky_tokens.json)에 반드시 있어야 한다 → 사전에서 빠지면 실패.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402

DATA = json.loads((ROOT / "docs/harness/naming_failures.json").read_text(encoding="utf-8"))
RISKY = json.loads((ROOT / "docs/harness/risky_tokens.json").read_text(encoding="utf-8"))
CASES = DATA["misreads"]


def test_schema():
    assert DATA["misreads"] and DATA["harness"] and DATA["process"]
    for c in CASES:
        assert set(c) >= {"names", "read_as", "token", "source"}, c
        assert c["names"] and c["read_as"] and c["source"]
        assert c["token"] is None or (isinstance(c["token"], str) and c["token"] == c["token"].lower())


@pytest.mark.parametrize("case", [c for c in CASES if c["token"]], ids=lambda c: c["token"])
def test_token_cases_caught_by_lint(case):
    assert case["token"] in RISKY, f'{case["token"]} 이 위험 단어 사전에 없음'
    rules = {f"N{i}": {"term": n} for i, n in enumerate(case["names"]) if "*" not in n}
    warned = {w.split()[0] for w in ct.lint_names(rules, RISKY)}
    assert warned == set(rules), f"lint_names가 놓친 이름: {set(rules) - warned}"


def test_untokenizable_cases_say_why():
    for c in CASES:
        if c["token"] is None:
            assert c.get("why_not_token"), c["names"]
