"""평가자 맥락 필드 명세 (docs/harness/name_harness_v2.md v2.2 '평가자 맥락').

사용자(2026-11-04): "평가자를 할 때도 목적, 차별점, 역할 따위 정보 등 답변자 보다 더 유리한 context를 갖고 있어야"
선택 필드: purpose, human_actions([명사, 술어] 1~3쌍), distinct_from(이웃 개념 → 이를 잡는 misread_as 분야 또는 contrasts 이름), role.
판정·해시에 쓰지 않는다(이미 받은 표본 보호). 답변자에게는 절대 보내지 않는다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402
import collect_samples as cs  # noqa: E402

BASE = {"id": "R01", "term": "merge-desk", "must": [["표", "excel"], {"label": "executor", "any": ["결정", "판단"]}],
        "must_not": ["자동 병합"]}
CTX = {**BASE,
       "purpose": "여러 소스의 표를 통합할 조건을 사람이 정하도록 돕는다",
       "human_actions": [["조건", "정한다"], ["근거", "남긴다"]],
       "distinct_from": {"SQL JOIN": "SQL", "자동 병합 도구": "auto-merge-tool"},
       "role": "studio 화면용 데이터셋 공급",
       "misread_as": {"SQL": ["sql 쿼리"]},
       "contrasts": ["auto-merge-tool"]}


# 1. 판정·해시는 맥락 필드의 영향을 받지 않는다
def test_context_not_in_hash():
    plain = {k: v for k, v in CTX.items() if k not in ("purpose", "human_actions", "distinct_from", "role")}
    assert ct.rule_hash(CTX) == ct.rule_hash(plain)


def test_context_not_in_judge():
    plain = {k: v for k, v in CTX.items() if k not in ("purpose", "human_actions", "distinct_from", "role")}
    for text in ("표를 사람이 결정", "표를 sql 쿼리로 결정", "표"):
        assert ct.judge(text, CTX) == ct.judge(text, plain)


# 2. 형식 검사
def test_lint_context_clean():
    assert ct.lint_context({"R01": CTX}) == []


def test_lint_context_no_context_rule_is_silent():
    """맥락 필드를 하나도 안 쓴 옛 규칙에는 경고하지 않는다(기존 규칙 파일 소음 방지)."""
    assert ct.lint_context({"R01": BASE}) == []


def test_lint_context_missing_purpose():
    r = {**CTX, "purpose": ""}
    assert any("purpose" in w for w in ct.lint_context({"R01": r}))


def test_lint_context_human_actions_shape():
    for bad in ([], [["조건"]], [["a", "b"]] * 4, [["조건", ""]], "조건을 정한다"):
        r = {**CTX, "human_actions": bad}
        assert any("human_actions" in w for w in ct.lint_context({"R01": r})), bad


# 3. 근거 연결: 평가자가 아는 것과 판정 단어가 따로 놀지 않게
def test_lint_context_distinct_without_backing():
    r = {**CTX, "distinct_from": {**CTX["distinct_from"], "git 병합": "git"}}
    warns = ct.lint_context({"R01": r})
    assert any("git 병합" in w and "근거 없음" in w for w in warns)


def test_lint_context_misread_without_source():
    r = {**CTX, "misread_as": {**CTX["misread_as"], "차트": ["시각화"]}}
    warns = ct.lint_context({"R01": r})
    assert any("차트" in w and "출처 없음" in w for w in warns)


def test_lint_context_distinct_may_point_to_contrast():
    r = {**CTX, "distinct_from": {"자동 병합 도구": "auto-merge-tool"}, "misread_as": {}}
    assert ct.lint_context({"R01": r}) == []


# 4. 누출 방지: 답변자에게는 id·term만
def test_context_never_sent_to_answerer(tmp_path):
    sent = []

    def fake(names, timeout):
        sent.append(json.dumps(names, ensure_ascii=False))
        return {"items": [{"id": n["id"], "term": n["term"], "explanation": "표를 사람이 결정"} for n in names]}
    cs.collect(fake, {"R01": CTX}, "r.json", 1, tmp_path / "o.jsonl", "fake-1", "fake", 5)
    assert sent
    for payload in sent:
        for leak in (CTX["purpose"], "정한다", "SQL JOIN", CTX["role"], "sql 쿼리", "표", "excel"):
            assert leak not in payload, leak
        assert all(set(n) == {"id", "term"} for n in json.loads(payload))


# 5. CLI
def test_cli_lint_prints_context(tmp_path):
    r = {**CTX, "distinct_from": {**CTX["distinct_from"], "git 병합": "git"}}
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"terms": [r]}, ensure_ascii=False), encoding="utf-8")
    s = tmp_path / "s.jsonl"
    s.write_text("", encoding="utf-8")
    out = subprocess.run([sys.executable, str(ROOT / "scripts/check_terms.py"), "--rules", str(p), "--samples", str(s),
                          "--lint"], capture_output=True, text=True, encoding="utf-8").stdout
    assert "lint-context:" in out and "git 병합" in out
