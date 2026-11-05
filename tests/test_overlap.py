"""한 묶음 이름끼리 뜻 겹침(check_terms.overlap) 명세 — 표 대조 GUI 세션 요청(2026-11-05).

이름마다 의도(must)가 다른 규칙 묶음에서, 이름 A의 설명문이 이름 B의 must를 모두 채우면 A→B 겹침으로 센다.
각 이름이 의도대로 읽혀도 서로 같은 뜻으로 읽히는 쌍을 잡는다. 규칙 기반, LLM 판정 없음.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402

TARGET = {"id": "S01", "term": "target", "must": [["대상"]], "must_not": []}
WANTS = {"id": "S02", "term": "wants", "must": [["원하는", "목표"]], "must_not": []}
ROLE = {"id": "S03", "term": "role", "must": [["역할"]], "must_not": []}
RULES = {r["id"]: r for r in (TARGET, WANTS, ROLE)}


def env(rule, text):
    return {"format": "samples/v2", "role": "target", "status": "ok", "items": [{"id": rule["id"], "term": rule["term"],
            "explanation": text}], "rule_hashes": {rule["id"]: ct.rule_hash(rule)}}


def test_overlap_counts_other_names_must(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in [
        env(TARGET, "목표로 삼는 대상"),      # target이 wants의 뜻으로도 읽힘
        env(TARGET, "다루는 대상"),
        env(WANTS, "원하는 상태"),
        env(ROLE, "맡은 역할"),
    ]), encoding="utf-8")
    ov = ct.overlap(RULES, [p])
    assert ov["S01"]["n"] == 2 and ov["S01"]["with"] == {"S02": 1}
    assert ov["S02"]["with"] == {} and ov["S03"]["with"] == {}
    assert ct.overlap_pairs(ov, RULES) == [("target", "wants", 1, 2)]


def test_overlap_skips_stale_and_rules_without_must(tmp_path):
    p = tmp_path / "s.jsonl"
    stale = env(TARGET, "목표로 삼는 대상")
    stale["rule_hashes"]["S01"] = "old"
    p.write_text(json.dumps(stale, ensure_ascii=False), encoding="utf-8")
    assert ct.overlap(RULES, [p])["S01"]["n"] == 0
    p.write_text(json.dumps(env(TARGET, "아무 설명"), ensure_ascii=False), encoding="utf-8")
    nomust = {**RULES, "S04": {"id": "S04", "term": "x", "must": [], "must_not": []}}
    assert ct.overlap(nomust, [p])["S01"]["with"] == {}  # must 없는 이름은 무엇이든 채우므로 비교 대상에서 뺀다


def test_overlap_cli(tmp_path):
    import namecheck
    r = tmp_path / "rules.json"
    r.write_text(json.dumps({"terms": list(RULES.values())}, ensure_ascii=False), encoding="utf-8")
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps(env(TARGET, "목표로 삼는 대상"), ensure_ascii=False), encoding="utf-8")
    assert namecheck.main(["overlap", "--rules", str(r), "--samples", str(p), "--json"]) == 2
