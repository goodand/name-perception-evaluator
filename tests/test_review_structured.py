"""대조 평가자 구조화된 출력 + 형식이 틀린 번호만 다시 묻기(수정 프로토콜, 사용자 2026-11-06).

평가자는 응답자와 달리 의도를 알고 보기 중에서 고르는 주체라 형식 신호의 영향이 작다 → 구조화된 출력을 쓴다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import review_explanations as rv  # noqa: E402

RULE = {"term": "name-x", "purpose": "이름 뜻을 본다", "human_actions": [], "distinct_from": {"뜻풀이": ""}}
TEXTS = ["뜻을 본다", "발음을 시험한다", "모르겠다"]


def body(prompt):
    return [l for l in prompt.split("설명:\n", 1)[1].splitlines() if l.strip()]


def test_structured_items_accepted():
    call = lambda p, t: {"items": [{"no": 1, "verdict": "같음", "read_as": ""},  # noqa: E731
                                   {"no": 2, "verdict": "다른 뜻", "read_as": "발음 시험"},
                                   {"no": 3, "verdict": "불분명", "read_as": ""}]}
    items, log = rv.ask(call, RULE, TEXTS, rv.INSTR_STRUCT.format(view=""), 10)
    assert [items[i]["verdict"] for i in range(3)] == ["같음", "다른 뜻", "불분명"] and len(log) == 1


def test_plain_missing_number_reasked_only():
    asked = []

    def call(p, t):
        asked.append(body(p))
        return "1. 같음\n3. 불분명" if len(asked) == 1 else "1. 다른 뜻 — 발음 시험"
    items, log = rv.ask(call, RULE, TEXTS, rv.INSTR.format(view=""), 10)
    assert asked[1] == ["1. 발음을 시험한다"]  # 빠진 2번만 다시, 번호는 새로 매긴다
    assert items[1] == {"verdict": "다른 뜻", "read_as": "발음 시험"} and len(log) == 2


def test_invalid_verdict_reasked():
    n = []

    def call(p, t):
        n.append(1)
        v = "애매함" if len(n) == 1 else "같음"
        return {"items": [{"no": i + 1, "verdict": v, "read_as": ""} for i in range(len(body(p)))]}
    items, _ = rv.ask(call, RULE, TEXTS, rv.INSTR_STRUCT.format(view=""), 10)
    assert len(n) == 2 and all(items[i]["verdict"] == "같음" for i in range(3))


def test_gives_up_after_max_rounds():
    calls = []
    items, log = rv.ask(lambda p, t: calls.append(1) or "형식 없음", RULE, TEXTS, rv.INSTR.format(view=""), 10)
    assert len(calls) == rv.MAX_ROUNDS and items == {} and log[-1]["pending"] == [0, 1, 2]


def test_review_counts_retries_and_error(tmp_path, monkeypatch):
    monkeypatch.setattr(rv, "explanations", lambda rules, files: {"C01": TEXTS})
    res = rv.review({"C01": RULE}, [], lambda p, t: "1. 같음" if len(body(p)) == 3 else "형식 없음", "end_user", 10)
    s = res["C01:end_user"] if "C01:end_user" in res else res["C01"]
    assert s["same"] == 1 and s["unclear"] == 2 and "응답 1/3" in s["error"] and s["rounds"] == rv.MAX_ROUNDS


def test_structured_prompt_has_no_line_format_example():
    assert "예:" not in rv.INSTR_STRUCT and "{view}" in rv.INSTR_STRUCT
