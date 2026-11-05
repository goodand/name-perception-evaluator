"""check_terms.py 명세 (docs/harness/name_harness_v2.md v2.1)."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402

REGRESSION_DELTA = {}  # 띄어쓰기 무시로 달라진 통과 수: 실측 0건(2026-11-04, names_rounds 5개 파일)

RULE = {"id": "R01", "term": "merge-desk", "intended": "사람이 결정", "candidates": ["a"],
        "must": [["표", "excel"], {"label": "executor", "any": ["결정", "판단"]}],
        "must_not": ["자동 병합"]}


def env(rule, items, status="ok", h=None, role="target"):
    return {"format": "samples/v2", "role": role, "status": status, "items": items,
            "rule_hashes": {rule["id"]: h or ct.rule_hash(rule)}}


def write_jsonl(p, lines):
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return p


# 정규화
@pytest.mark.parametrize("text", ["Excel 표를 사람이 결정", "EXCEL로 판단", "excel 판 단"])
def test_case_and_space_insensitive(text):
    assert ct.judge(text, RULE)[0]


def test_must_not_space_insensitive():
    ok, why = ct.judge("표를 자동병합하고 결정", RULE)
    assert not ok and any("자동 병합" in w for w in why)


def test_hyphen_kept():
    rule = {"must": [["read-only"]], "must_not": []}
    assert not ct.judge("read only 모드", rule)[0]


# 이름표 그룹
def test_labeled_group_reason():
    ok, why = ct.judge("표를 자동으로 합친다", RULE)
    assert not ok and why == ["누락[executor]: 결정|판단"]


def test_plain_group_unchanged_reason():
    ok, why = ct.judge("결정", RULE)
    assert why == ["누락: 표|excel"]


# 해시
def test_hash_ignores_intended_candidates_and_order():
    r2 = dict(RULE, intended="다른 뜻", candidates=[], must=[{"label": "executor", "any": ["판단", "결정"]}, ["excel", "표"]])
    assert ct.rule_hash(RULE) == ct.rule_hash(r2)


@pytest.mark.parametrize("change", [{"term": "other"}, {"must_not": []}, {"must": [["표"]]}])
def test_hash_changes(change):
    assert ct.rule_hash(RULE) != ct.rule_hash(dict(RULE, **change))


def test_hash_includes_judge_version(monkeypatch):
    h = ct.rule_hash(RULE)
    monkeypatch.setattr(ct, "JUDGE_VERSION", "test")
    assert ct.rule_hash(RULE) != h


# 형식 통일
def test_to_items_formats():
    it = [{"id": "R01", "term": "t", "explanation": "e"}]
    assert ct.to_items(it) == it
    assert ct.to_items({"items": it}) == it
    assert ct.to_items({"status": "succeeded", "output": {"items": it}}) == it
    assert ct.to_items({"status": "failed", "output": None}) is None
    assert ct.to_items({"status": "succeeded", "output": None}) is None
    assert ct.to_items(env(RULE, it)) == it
    assert ct.to_items(env(RULE, it, status="failed")) is None


def test_legacy_dict_of_models():
    it = [{"id": "R01", "term": "t", "explanation": "e"}]
    assert ct.legacy_samples({"note": "x", "sonnet": it, "haiku": it}) == [it, it]


# 집계: stale·legacy·mismatch·중복·실패·대조
def test_score_counts(tmp_path):
    good = {"id": "R01", "term": "merge-desk", "explanation": "표를 사람이 결정"}
    bad = {"id": "R01", "term": "merge-desk", "explanation": "표를 자동 병합"}
    f = write_jsonl(tmp_path / "s.jsonl", [
        env(RULE, [good]), env(RULE, [bad]), env(RULE, [], status="failed"),
        env(RULE, [good], h="oldhash000000"),
        env(RULE, [dict(good, term="ldx")]),
        env(RULE, [good, good]),
        env(RULE, [{"id": "R01", "term": "auto-merge-tool", "explanation": "자동 병합 도구"}], role="contrast"),
    ])
    legacy = tmp_path / "old.json"
    legacy.write_text(json.dumps([[good]], ensure_ascii=False), encoding="utf-8")
    s = ct.score({"R01": RULE}, [f, legacy])["R01"]
    assert (s["pass"], s["n"]) == (1, 2)
    assert s["failed"] == 1 and s["stale"] == 1 and s["mismatch"] == 1
    assert s["duplicate"] == 1 and s["legacy"] == 1
    assert s["contrast"] == {"auto-merge-tool": [0, 1]}
    s2 = ct.score({"R01": RULE}, [f, legacy], allow_stale=True, allow_legacy=True)["R01"]
    assert (s2["pass"], s2["n"]) == (3, 4)


# lint
def test_lint():
    warns = ct.lint_rules({"R01": {"term": "x", "must": [["표", "결정"], ["표", "table"]], "must_not": []}})
    assert len(warns) == 1 and "R01" in warns[0]


# 지연 import
def test_no_yaml_needed():
    code = ("import sys; sys.modules['yaml']=None; sys.path.insert(0, r'%s'); import check_terms as c; "
            "print(c.judge('표', {'must':[['표']]})[0], c.to_items([]))") % (ROOT / "scripts")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.split() == ["True", "[]"], out.stderr


def test_load_rules_json(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps([RULE], ensure_ascii=False), encoding="utf-8")
    assert ct.load_rules(p)["R01"]["term"] == "merge-desk"


# 회귀: 띄어쓰기 무시 외에는 패치 전과 같아야 함
def test_regression_names_rounds():
    base = json.loads((ROOT / "tests/baseline_names_rounds.json").read_text(encoding="utf-8"))
    for name, (n, passed, rules_file) in base.items():
        rules = ct.load_rules(ROOT / "docs/glossary" / rules_file)
        S = [s for s in ct.legacy_samples(json.loads((ROOT / "docs/glossary/names_rounds" / name).read_text(encoding="utf-8"))) if s]
        assert len(S) == n
        now = sum(ct.judge(i.get("explanation", ""), rules[i["id"]])[0] for s in S for i in s if i.get("id") in rules)
        assert now == passed + REGRESSION_DELTA.get(name, 0), name
