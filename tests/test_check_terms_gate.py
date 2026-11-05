"""check_terms.py 오독 게이트·부트스트랩·위험 단어 검사 명세 (docs/harness/name_harness_v2.md v2.2).

사용자 규칙(2026-11-04): 6회 중 1회라도 오독이면 그 이름은 제외하고 다른 이름을 고른다.
선택 규칙은 workflow-runner runner.choose()와 같다: 필수 게이트 → 통과율 → 동점이면 기존안 유지.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402

BASE = {"id": "R01", "term": "merge-desk", "must": [["표", "excel"], {"label": "executor", "any": ["결정", "판단"]}],
        "must_not": ["자동 병합"]}
BASE_HASH = "90edc37d56b9"  # f60ed11 판정기로 잰 값. 바뀌면 이미 받은 v2 표본이 전부 stale로 떨어진다
MIS = {**BASE, "misread_as": {"SQL": ["on 절", "join"], "git": ["브랜치"]}}


def env(rule, items, backend="gpt", role="target", status="ok"):
    return {"format": "samples/v2", "role": role, "status": status, "backend": backend, "items": items,
            "rule_hashes": {rule["id"]: ct.rule_hash(rule)}}


def item(rule, text):
    return [{"id": rule["id"], "term": rule["term"], "explanation": text}]


def write_jsonl(p, lines):
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return p


# 1. misread_as가 없는 규칙은 그대로: 해시·판정 모두 (JUDGE_VERSION을 올리지 않는 근거)
def test_hash_unchanged_without_misread():
    assert ct.rule_hash(BASE) == BASE_HASH
    assert ct.rule_hash({**BASE, "misread_as": {}}) == BASE_HASH


def test_judge_unchanged_without_misread():
    assert ct.judge("표를 자동병합하고 결정", BASE) == (False, ["오해 신호: 자동 병합"])
    assert ct.judge("표를 사람이 결정", BASE) == (True, [])


def test_judge_version_not_bumped():
    assert ct.JUDGE_VERSION == "2"


# 2. misread_as가 있으면 해시에 들어가고, 신호가 나오면 분야 이름으로 실패
def test_hash_includes_misread():
    assert ct.rule_hash(MIS) != BASE_HASH
    other = {**BASE, "misread_as": {"SQL": ["on 절"]}}
    assert ct.rule_hash(other) != ct.rule_hash(MIS)


def test_hash_misread_order_insensitive():
    flip = {**BASE, "misread_as": {"git": ["브랜치"], "SQL": ["join", "on 절"]}}
    assert ct.rule_hash(flip) == ct.rule_hash(MIS)


def test_judge_misread_reason():
    ok, why = ct.judge("표를 JOIN해서 결정", MIS)
    assert not ok and any(w.startswith("misread:SQL") for w in why)


def test_misread_space_insensitive():
    assert not ct.judge("표의 ON절로 결정", MIS)[0]


def test_misread_one_reason_per_field():
    ok, why = ct.judge("표를 join, ON 절로 결정", MIS)
    assert sum(w.startswith("misread:SQL") for w in why) == 1


# 3. 게이트: 6회 중 1회라도 오독이면 제외
def test_score_counts_misread_and_excludes(tmp_path):
    good = [env(MIS, item(MIS, "표를 사람이 결정"), b) for b in ("gpt", "claude") for _ in range(3)]
    bad = good[:5] + [env(MIS, item(MIS, "표를 브랜치처럼 결정"), "claude")]
    res = ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", bad)])
    s = res["R01"]
    assert (s["pass"], s["n"]) == (5, 6)
    assert s["misread"] == {"git": 1}
    assert s["excluded"] is True


def test_not_excluded_without_misread(tmp_path):
    good = [env(MIS, item(MIS, "표를 사람이 결정"))] * 6
    assert ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", good)])["R01"]["excluded"] is False


def test_must_not_alone_does_not_exclude(tmp_path):
    """must_not은 통과 실패일 뿐 오독 게이트가 아니다(분야가 없는 신호)."""
    lines = [env(MIS, item(MIS, "표를 자동병합하고 결정"))] + [env(MIS, item(MIS, "표를 사람이 결정"))] * 5
    s = ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", lines)])["R01"]
    assert (s["pass"], s["excluded"]) == (5, False)


def test_contrast_misread_not_counted(tmp_path):
    con = env(MIS, [{"id": "R01", "term": "auto-merge-tool", "explanation": "git 브랜치 자동 병합"}], role="contrast")
    s = ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", [con])])["R01"]
    assert s["misread"] == {} and s["excluded"] is False


# 4. 선택: runner.choose()와 같은 순서
def _res(**kw):
    """(pass, n, excluded[, baseline[, misread_n]]). misread_n 기본: 제외면 1, 아니면 0."""
    return {k: {"term": k, "pass": v[0], "n": v[1], "excluded": v[2], "baseline": v[3] if len(v) > 3 else False,
                "misread_n": v[4] if len(v) > 4 else int(v[2])} for k, v in kw.items()}


def test_choose_skips_excluded():
    out = ct.choose(_res(a=(6, 6, True), b=(5, 6, False)))
    assert out["selected"] == "b"


def test_choose_ties_keep_baseline():
    assert ct.choose(_res(a=(6, 6, False), b=(6, 6, False, True)))["selected"] == "b"
    assert ct.choose(_res(a=(6, 6, False, True), b=(6, 6, False)))["selected"] == "a"


# 예비 선택(사용자, 2026-11-04): "너무 많이 소거해서 이름 후보 생성에 한계가 생기면 오독률이 낮은 것들 중에서 골라야지"
def test_choose_fallback_lowest_misread_rate_when_all_excluded():
    out = ct.choose(_res(a=(6, 6, True, False, 3), b=(4, 6, True, False, 1), c=(6, 6, True, False, 2)))
    assert out["selected"] == "b" and out["fallback"] is True  # 통과율이 낮아도 오독률 최저가 먼저


def test_choose_fallback_then_pass_rate_then_baseline():
    out = ct.choose(_res(a=(3, 6, True, False, 1), b=(5, 6, True, False, 1), c=(6, 6, True, False, 2)))
    assert out["selected"] == "b"  # 오독률 같은 a·b 중 통과율
    tie = ct.choose(_res(a=(5, 6, True, False, 1), b=(5, 6, True, True, 1)))
    assert tie["selected"] == "b"  # 그다음 동점은 기존안 유지


def test_choose_fallback_uses_rate_not_count():
    """1/30이 1/6보다 낮다: 횟수가 아니라 비율."""
    out = ct.choose(_res(a=(6, 6, True, False, 1), b=(20, 30, True, False, 1)))
    assert out["selected"] == "b"


def test_choose_normal_is_not_fallback():
    out = ct.choose(_res(a=(6, 6, True, False, 1), b=(3, 6, False)))
    assert out["selected"] == "b" and out["fallback"] is False


def test_misread_n_counts_samples_not_fields(tmp_path):
    lines = [env(MIS, item(MIS, "표를 join해 브랜치처럼 결정"))] + [env(MIS, item(MIS, "표를 사람이 결정"))] * 5
    s = ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", lines)])["R01"]
    assert s["misread"] == {"SQL": 1, "git": 1} and s["misread_n"] == 1


def test_cli_shows_misread_rate_for_excluded(tmp_path):
    rules_p = tmp_path / "r.json"
    rules_p.write_text(json.dumps({"terms": [MIS]}, ensure_ascii=False), encoding="utf-8")
    lines = [env(MIS, item(MIS, "표를 사람이 결정"))] * 5 + [env(MIS, item(MIS, "표를 join해 결정"))]
    out = subprocess.run([sys.executable, str(ROOT / "scripts/check_terms.py"), "--rules", str(rules_p), "--samples",
                          str(write_jsonl(tmp_path / "s.jsonl", lines))], capture_output=True, text=True,
                         encoding="utf-8").stdout
    assert "오독률 1/6 (17%)" in out and "예비 선택: merge-desk" in out


def test_choose_ignores_unsampled():
    assert ct.choose(_res(a=(0, 0, False), b=(3, 6, False)))["selected"] == "b"


# 5. 0회 오독의 남은 위험: Wilson 95% 상한
@pytest.mark.parametrize("k,n,lo,hi", [(0, 6, 0.38, 0.40), (1, 6, 0.55, 0.58), (0, 30, 0.10, 0.12)])  # 손계산 0.390·0.564·0.114
def test_wilson_upper(k, n, lo, hi):
    assert lo <= ct.wilson_upper(k, n) <= hi


def test_wilson_upper_empty():
    assert ct.wilson_upper(0, 0) == 1.0


# 7. 위험 단어 사전: 수집 전 경고
def test_lint_names():
    risky = {"engine": "실행·판정 엔진", "decision": "의사결정 테이블"}
    rules = {"R01": {"term": "decision-tabular-engine"}, "R02": {"term": "name_semantic_harness"}}
    warns = ct.lint_names(rules, risky)
    assert len(warns) == 2 and all(w.startswith("R01") for w in warns)


def test_risky_tokens_file_valid():
    p = ROOT / "docs/harness/risky_tokens.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data and all(isinstance(k, str) and k == k.lower() and isinstance(v, str) and v for k, v in data.items())


# 9. 적대 검토 보완(2026-11-04, opus 검토자): 틀린 구현이 통과하던 곳
def test_hash_same_field_different_words():
    other = {**BASE, "misread_as": {"SQL": ["on 절", "join"], "git": ["merge"]}}
    assert ct.rule_hash(other) != ct.rule_hash(MIS)


def test_misread_reason_exact_and_per_field():
    ok, why = ct.judge("표를 join해 브랜치처럼 결정", MIS)
    assert [w for w in why if w.startswith("misread:")] == ["misread:SQL: join", "misread:git: 브랜치"]


def test_misread_counted_per_sample(tmp_path):
    lines = [env(MIS, item(MIS, "표를 join과 ON 절로 결정"))]
    assert ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", lines)])["R01"]["misread"] == {"SQL": 1}


def test_one_in_thirty_still_excluded(tmp_path):
    lines = [env(MIS, item(MIS, "표를 사람이 결정"))] * 29 + [env(MIS, item(MIS, "표를 join해 결정"))]
    assert ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", lines)])["R01"]["excluded"] is True


def test_excluded_keeps_evidence(tmp_path):
    """보수적 판정이라 오탐이 가능 → 제외 근거 설명문을 그대로 남겨 사람이 확인한다."""
    lines = [env(MIS, item(MIS, "SQL JOIN과는 다르게 표를 사람이 결정"))]
    s = ct.score({"R01": MIS}, [write_jsonl(tmp_path / "a.jsonl", lines)])["R01"]
    assert s["excluded"] is True  # 부정문도 제외: 의도된 보수적 동작(LLM 판정 금지)
    assert s["misread_examples"] == ["SQL JOIN과는 다르게 표를 사람이 결정"]


def test_stale_misread_not_counted(tmp_path):
    stale = {**env(MIS, item(MIS, "표를 join해 결정")), "rule_hashes": {"R01": "000000000000"}}
    p = write_jsonl(tmp_path / "a.jsonl", [stale])
    assert ct.score({"R01": MIS}, [p])["R01"]["excluded"] is False
    assert ct.score({"R01": MIS}, [p], allow_stale=True)["R01"]["excluded"] is True


def test_score_carries_baseline(tmp_path):
    r = {**MIS, "baseline": True}
    lines = [env(r, item(r, "표를 사람이 결정"))]
    res = ct.score({"R01": r}, [write_jsonl(tmp_path / "a.jsonl", lines)])
    assert res["R01"]["baseline"] is True
    assert ct.choose(res)["selected"] == "merge-desk"


def test_choose_tie_without_baseline_is_first_id():
    assert ct.choose(_res(a=(6, 6, False), b=(6, 6, False)))["selected"] == "a"


def test_lint_names_length():
    """사용자(2026-11-04): '이름에서 키워드가 4개면 긴 편인 것 같아' → 조각 4개 이상 경고(비차단)."""
    rules = {"A": {"term": "name-misread-check-harness"}, "B": {"term": "name_semantic_harness"},
             "C": {"term": "tabular-compare-engine"}, "D": {"term": "table_join_condition_x"}}
    warns = [w for w in ct.lint_names(rules, {}) if "길이" in w]
    assert [w.split()[0] for w in warns] == ["A", "D"]
    assert "키워드 4개" in warns[0]


def test_lint_names_case_insensitive():
    assert ct.lint_names({"R01": {"term": "Decision-Engine"}}, {"engine": "x"})


def test_risky_tokens_seeded_from_cases():
    data = json.loads((ROOT / "docs/harness/risky_tokens.json").read_text(encoding="utf-8"))
    for tok in ("engine", "decision", "studio", "grid", "resolver", "venn"):
        assert tok in data, tok


def test_cli_shows_zero_misread_upper(tmp_path):
    rules_p = tmp_path / "r.json"
    rules_p.write_text(json.dumps({"terms": [MIS]}, ensure_ascii=False), encoding="utf-8")
    s = write_jsonl(tmp_path / "s.jsonl", [env(MIS, item(MIS, "표를 사람이 결정"))] * 6)
    out = subprocess.run([sys.executable, str(ROOT / "scripts/check_terms.py"), "--rules", str(rules_p), "--samples",
                          str(s)], capture_output=True, text=True, encoding="utf-8").stdout
    assert "6/6" in out and "오독 0/6 (95% 상한 39%)" in out and "선택: merge-desk" in out


def test_no_bootstrap():
    """재표본 부트스트랩은 뺐다: 표본은 전수 집계한다(사용자, 2026-11-04)."""
    assert not hasattr(ct, "bootstrap")


# 8. CLI
def test_cli_gate_full_count(tmp_path):
    rules_p = tmp_path / "r.json"
    rules_p.write_text(json.dumps({"terms": [MIS]}, ensure_ascii=False), encoding="utf-8")
    lines = [env(MIS, item(MIS, "표를 사람이 결정"))] * 5 + [env(MIS, item(MIS, "표를 join해 결정"))]
    s = write_jsonl(tmp_path / "s.jsonl", lines)
    out = subprocess.run([sys.executable, str(ROOT / "scripts/check_terms.py"), "--rules", str(rules_p), "--samples",
                          str(s)], capture_output=True, text=True, encoding="utf-8").stdout
    assert "5/6" in out and "제외" in out and "오독 SQL 1" in out and "예비 선택: merge-desk" in out
    assert "부트스트랩" not in out
