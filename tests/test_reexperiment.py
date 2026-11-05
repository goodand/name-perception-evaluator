"""답변자·평가자 재실험 명세 (docs/harness/name_harness_v2.md v2.2 '재실험').

사용자(2026-11-04): "답변자와 평가가를 분리해서 본다면 그것을 또 재실험을 각각 할 수 있겠네" / "둘 다 해"
- 답변자 재실험: 지시문(상황 설명)만 바꿔 다시 수집 → instr_sha별 집계. 게이트 판정이 지시문마다 다르면 '지시문 취약'.
- 평가자 재실험: 같은 답변에 규칙 변형 여러 개 → 변형별 판정. 제외 여부나 선택이 다르면 '규칙 민감'. 호출 없음.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402
import collect_samples as cs  # noqa: E402
import collect_variants as cv  # noqa: E402

R = {"id": "R01", "term": "merge-desk", "must": [["표"], ["결정"]], "must_not": [], "misread_as": {"SQL": ["sql"]}}
R2 = {**R, "id": "R02", "term": "grid-desk"}


def env(rule, text, instr="aaa", backend="gpt"):
    return {"format": "samples/v2", "role": "target", "status": "ok", "backend": backend, "instr_sha": instr,
            "items": [{"id": rule["id"], "term": rule["term"], "explanation": text}],
            "rule_hashes": {rule["id"]: ct.rule_hash(rule)}}


def jl(p, lines):
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return p


# ---- 답변자 재실험: 집계 ----
def test_score_env_filter(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa"), env(R, "표", "bbb")])
    s = ct.score({"R01": R}, [p], env_filter=lambda e: e.get("instr_sha") == "bbb")["R01"]
    assert (s["pass"], s["n"]) == (0, 1)


def test_score_without_filter_unchanged(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa"), env(R, "표", "bbb")])
    s = ct.score({"R01": R}, [p])["R01"]
    assert (s["pass"], s["n"]) == (1, 2)


def test_split_scores_by_instr(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa")] * 3 + [env(R, "표를 sql로 결정", "bbb")] * 3)
    groups = ct.split_scores({"R01": R}, [p], "instr_sha")
    assert set(groups) == {"aaa", "bbb"}
    assert groups["aaa"]["R01"]["excluded"] is False and groups["bbb"]["R01"]["excluded"] is True


def test_split_scores_legacy_group(tmp_path):
    p = tmp_path / "old.json"
    p.write_text(json.dumps([[{"id": "R01", "term": "merge-desk", "explanation": "표를 결정"}]]), encoding="utf-8")
    groups = ct.split_scores({"R01": R}, [p], "instr_sha", allow_legacy=True)
    assert list(groups) == ["legacy"]


def test_stability_flags_instruction_fragile(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa")] * 3 + [env(R, "표를 sql로 결정", "bbb")]
           + [env(R2, "표를 결정", "aaa")] * 3 + [env(R2, "표를 결정", "bbb")] * 3)
    st = ct.stability(ct.split_scores({"R01": R, "R02": R2}, [p], "instr_sha"))
    assert st["R01"]["consistent"] is False and st["R02"]["consistent"] is True
    assert st["R01"]["groups"]["bbb"] == (0, 1, True)


def test_stability_ignores_unsampled_groups(tmp_path):
    """한 지시문에 어떤 이름 표본이 없으면 그 칸은 비교에서 뺀다(없는 것 ≠ 통과)."""
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa")] + [env(R2, "표를 결정", "bbb")])
    st = ct.stability(ct.split_scores({"R01": R, "R02": R2}, [p], "instr_sha"))
    assert st["R01"]["groups"] == {"aaa": (1, 1, False)} and st["R01"]["consistent"] is True


# ---- 평가자 재실험: 규칙 변형 ----
def test_variants_rule_sensitive(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 사람이 결정", "aaa")] * 3)
    loose = {"R01": R}
    strict = {"R01": {**R, "misread_as": {"SQL": ["sql"], "사람": ["사람이"]}}}
    out = ct.evaluate_variants({"V0": loose, "V1": strict}, [p])
    assert out["by_variant"]["V0"]["R01"]["excluded"] is False
    assert out["by_variant"]["V1"]["R01"]["excluded"] is True  # 해시가 달라도 같은 답변을 다시 판정
    assert out["sensitive"]["R01"] is True


def test_variants_stable(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa")] * 3)
    out = ct.evaluate_variants({"V0": {"R01": R}, "V1": {"R01": {**R, "must": [["표", "테이블"], ["결정"]]}}}, [p])
    assert out["sensitive"]["R01"] is False


def test_variants_selection_changes(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정", "aaa")] * 2 + [env(R2, "표를 결정", "aaa"), env(R2, "표", "aaa")])
    v0 = {"R01": R, "R02": R2}
    v1 = {"R01": {**R, "must": [["표"], ["승인"]]}, "R02": {**R2, "must": [["표"]]}}
    out = ct.evaluate_variants({"V0": v0, "V1": v1}, [p])
    assert out["selected"] == {"V0": "merge-desk", "V1": "grid-desk"} and out["selection_sensitive"] is True


def test_variants_not_sensitive_when_never_selectable(tmp_path):
    """모든 변형에서 통과 0이면 제외 표시가 갈려도 '규칙 민감'이 아니다(어느 쪽이든 못 고름). s14 naming-harness 실측."""
    p = jl(tmp_path / "a.jsonl", [env(R, "규칙을 sql로 본다", "aaa")] * 3)
    out = ct.evaluate_variants({"V0": {"R01": {**R, "misread_as": {}}}, "V1": {"R01": R}}, [p])
    assert out["by_variant"]["V1"]["R01"]["excluded"] is True and out["by_variant"]["V0"]["R01"]["pass"] == 0
    assert out["sensitive"]["R01"] is False


def test_variants_require_same_terms(tmp_path):
    p = jl(tmp_path / "a.jsonl", [env(R, "표를 결정")])
    with pytest.raises(ValueError):
        ct.evaluate_variants({"V0": {"R01": R}, "V1": {"R01": {**R, "term": "other"}}}, [p])


def test_variants_keep_term_mismatch_protection(tmp_path):
    """해시는 무시하지만 (id, term) 짝 검사는 유지: 다른 이름의 옛 표본으로 판정하지 않는다."""
    other = {**R, "term": "old-name"}
    p = jl(tmp_path / "a.jsonl", [env(other, "표를 결정")])
    out = ct.evaluate_variants({"V0": {"R01": R}, "V1": {"R01": R}}, [p])
    assert out["by_variant"]["V0"]["R01"]["n"] == 0


# ---- 답변자 재실험: 수집 ----
def test_compose_keeps_output_contract():
    text = cv.compose("이 이름을 GitHub 목록에서 처음 본 사람이라고 가정하세요.")
    assert text.startswith("이 이름을 GitHub 목록에서")
    assert cv.CONTRACT in text and "items" not in text  # 평문: 형식 요구 없음
    assert cv.CONTRACT in cs.INSTR  # 계약 부분은 원본 지시문에서 그대로 가져온다


def test_collect_variant_records_instr_sha(tmp_path):
    seen = []

    def fake(names, timeout):
        seen.append(cs.INSTR)
        return {"items": [{"id": n["id"], "term": n["term"], "explanation": "표를 결정"} for n in names]}
    before = cs.INSTR
    out = cv.collect_variant(fake, "V1", "가정 문장.", {"R01": R}, "r.json", 1, tmp_path, "fake-1", "fake", 5)
    assert cs.INSTR == before  # 끝나면 원래 지시문으로 복구
    rec = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert rec["instr_sha"] == cv.sha(cv.compose("가정 문장."))
    assert seen and all(s == cv.compose("가정 문장.") for s in seen)
    assert out.name.endswith("_V1.jsonl")


def test_collect_variant_restores_on_error(tmp_path):
    def boom(names, timeout):
        raise RuntimeError("x")
    before = cs.INSTR
    cv.collect_variant(boom, "V2", "가정.", {"R01": R}, "r.json", 1, tmp_path, "m", "fake", 5)
    assert cs.INSTR == before
