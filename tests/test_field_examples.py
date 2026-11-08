"""오독 두 종류(사용자 2026-11-06 "뜻이 잘못되었다기보다 분야의 예시가 잘못된 케이스"):
역할 오독은 제외, 분야 예시 어긋남은 경고만.
- 브리프 field_examples {분야: [신호어]}: 이 신호는 처음부터 분야 예시(경고)
- 브리프 example_context: true면 misread_as 신호가 예를 드는 말("특히", "예를 들어", "…등", "같은") 바로 뒤·앞에 있을 때 분야 예시로 낮춘다
둘 다 없는 규칙은 판정·해시가 예전과 같다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import check_terms as ct  # noqa: E402

BASE = {"term": "용례 조사원", "must": [{"label": "찾기", "any": ["조사", "찾"]}],
        "misread_as": {"사전 편찬": ["사전을 만드", "편찬"]}}
CASE = "단어가 실제로 어떻게 쓰이는지 조사하는 사람, 특히 사전 편찬이나 언어 연구에 필요한 예시를 찾는다."
ROLE = "사전을 만드는 편찬 담당자다."


def test_old_rule_unchanged():
    ok, why = ct.judge(CASE, BASE)
    assert not ok and any(w.startswith("misread:사전 편찬") for w in why)
    assert ct.rule_hash(BASE) == ct.rule_hash(dict(BASE))


def test_example_context_downgrades():
    r = {**BASE, "example_context": True}
    ok, why = ct.judge(CASE, r)
    assert ok and ct.field_example_hits(ct.norm(CASE), r) == [("사전 편찬", "편찬")]
    assert ct.rule_hash(r) != ct.rule_hash(BASE)


def test_role_misread_still_excluded():
    r = {**BASE, "example_context": True}
    ok, why = ct.judge(ROLE, r)
    assert not ok and ct.misread_hits(ct.norm(ROLE), r) == [("사전 편찬", "사전을 만드")]


def test_field_examples_list_is_warning_only():
    r = {**BASE, "misread_as": {"사전 편찬": ["사전을 만드"]}, "field_examples": {"사전 편찬": ["편찬"]}}
    ok, _ = ct.judge("단어 쓰임을 조사한다. 편찬에도 쓰인다.", r)
    assert ok and ct.field_example_hits(ct.norm("편찬에도 쓰인다"), r) == [("사전 편찬", "편찬")]


def test_score_counts_field_examples(tmp_path):
    import json
    r = {"id": "C01", **BASE, "example_context": True}
    f = tmp_path / "s.jsonl"
    f.write_text(json.dumps({"format": "samples/v2", "role": "target", "status": "ok", "rule_hashes": {"C01": ct.rule_hash(r)},
                             "items": [{"id": "C01", "term": r["term"], "explanation": CASE}]}, ensure_ascii=False) + "\n",
                 encoding="utf-8")
    s = ct.score({"C01": r}, [f])["C01"]
    assert s["pass"] == 1 and not s["excluded"] and s["field_examples"] == {"사전 편찬": 1}


def test_listing_is_not_example():  # 반례: "이나"로 나열한 맡은 일은 역할 오독
    r = {**BASE, "example_context": True}
    text = "용어를 기록하는 사람. 사전 편찬이나 용어 표준화 등의 업무를 담당하는 역할이다."
    assert ct.misread_hits(ct.norm(text), r) == [("사전 편찬", "편찬")]
