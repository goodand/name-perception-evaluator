"""이름 후보 생성·키워드 통계 명세 (scripts/name_keywords.py).

사용자(2026-11-04): "후보군을 20개씩 5개 만들면 그 안에 있는 키워드들로 통계를 내는 것도 가능하겠네"
- 생성은 격리(하는 일·사람 행동만, 분야 이름·금지 목록·실패 단어 없음)
- 통계: 키워드별 등장 횟수, 묶음 등장 수(독립 생성 중 몇 묶음에 나왔나), 함께 쓰인 단어
- 검증 결과를 키워드 단위로 모은 오독률·통과율
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import name_keywords as nk  # noqa: E402


def test_normalize():
    assert nk.normalize(" Meaning Forecast ") == "meaning-forecast"
    assert nk.normalize("sense_preview") == "sense_preview"
    assert nk.normalize("name--insight!") == "name-insight"
    assert nk.normalize("") == ""


def test_tokens():
    assert nk.tokens("name-interpretation") == ["name", "interpretation"]
    assert nk.tokens("a_b-c") == ["a", "b", "c"]


def test_keyword_stats_counts_and_batches():
    batches = [["meaning-forecast", "name-preview"], ["meaning-check"], ["name-lens", "meaning-name"]]
    st = nk.keyword_stats(batches)
    assert st["meaning"]["count"] == 3 and st["meaning"]["batches"] == 3
    assert st["name"]["count"] == 3 and st["name"]["batches"] == 2
    assert st["forecast"] == {"count": 1, "batches": 1, "names": ["meaning-forecast"]}


def test_keyword_stats_dedup_within_batch_for_batches():
    """같은 묶음 안에서 여러 번 나와도 묶음 등장 수는 1, 이름이 중복이면 한 번만 센다."""
    st = nk.keyword_stats([["name-a", "name-b", "name-a"]])
    assert st["name"]["batches"] == 1 and st["name"]["count"] == 2


def test_ranked_order():
    """정렬: 묶음 등장 수 → 등장 횟수 → 알파벳."""
    st = nk.keyword_stats([["x-a"], ["x-b"], ["y-a", "y-c"]])
    assert [k for k, _ in nk.ranked(st)] == ["a", "x", "y", "b", "c"]  # y는 묶음 1개지만 이름 2개


def test_diversity_by_source():
    """생성자 비교(사용자: 'gpt 쪽이 훨씬 다양하고 창의적으로 보이긴 한데 … 판단을 하긴 해야겠네')."""
    by = {"gpt": [["meaning-forecast", "sense-preview"], ["meaning-probe"]],
          "haiku": [["name-check", "name-test"], ["name-check", "name-review"]]}
    d = nk.diversity(by)
    assert d["gpt"]["distinct_tokens"] == 5 and d["haiku"]["distinct_tokens"] == 4
    assert d["gpt"]["unique_tokens"] == 5 and d["haiku"]["unique_tokens"] == 4
    assert d["haiku"]["within_overlap"] > d["gpt"]["within_overlap"]  # 다시 돌리면 같은 단어 반복
    assert d["gpt"]["names"] == 3 and d["haiku"]["names"] == 3  # 서로 다른 이름 수


def test_pairs():
    pr = nk.pairs([["meaning-preview", "meaning-preview-x", "meaning-preview"], ["preview-meaning"]])
    assert pr[("meaning", "preview")] == 3  # 서로 다른 이름 단위, 순서 무시, 같은 이름 중복은 한 번


def test_parse_candidates():
    out = {"candidates": [{"name": "Meaning Forecast", "why": "x"}, {"name": "meaning-forecast"}, {"why": "no name"}]}
    assert nk.parse_candidates(out) == [{"name": "meaning-forecast", "why": "x"}]
    assert nk.parse_candidates(None) == []
    assert nk.parse_candidates({"items": []}) == []


def test_prompt_is_isolated():
    """생성 프롬프트에 분야 이름·금지 목록·이전 실패 단어가 없다."""
    p = nk.GEN_PROMPT.lower()
    for bad in ("소프트웨어", "저장소", "repository", "repo", "semantic", "linter", "naming", "오독", "하지 마",
                "금지", "실패", "harness"):
        assert bad not in p, bad
    assert "20" in nk.GEN_PROMPT and " — " in nk.GEN_PROMPT  # 평문 한 줄 형식


def test_gen_prompt_from_brief_is_generic():
    """생성 프롬프트는 프로필 틀 + 브리프(목적·사람 행동)로 만든다 — 다른 주제에도 쓴다(사용자: 포괄성)."""
    import json
    prof = json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8"))
    brief = {"purpose": "흩어진 표를 대조해 남길 조건을 정하게 돕는다",
             "human_actions": [["표", "대조한다"], ["조건", "정한다"]]}
    p = nk.gen_prompt(brief, prof, 12)
    assert brief["purpose"] in p and "표를 대조한다" in p and "조건을 정한다" in p
    assert "12" in p and "1~3" in p and " — " in p
    assert "받아들여진 뜻" not in p  # 다른 주제의 내용이 섞이지 않음


def test_default_prompt_equals_brief_prompt():
    import json
    prof = json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8"))
    brief = json.loads((ROOT / "docs/harness/briefs/name-harness.json").read_text(encoding="utf-8"))
    assert nk.GEN_PROMPT == nk.gen_prompt(brief, prof, 20)


def test_token_outcomes():
    res = {"E1": {"term": "meaning-forecast", "pass": 5, "n": 6, "misread_n": 1, "excluded": True},
           "E2": {"term": "meaning-preview", "pass": 6, "n": 6, "misread_n": 0, "excluded": False},
           "E3": {"term": "name-preview", "pass": 0, "n": 0, "misread_n": 0, "excluded": False}}
    to = nk.token_outcomes(res)
    assert to["meaning"] == {"names": 2, "pass": 11, "n": 12, "misread_n": 1, "excluded": 1}
    assert to["preview"]["n"] == 6  # 표본 0개 이름은 n에 안 더함
    assert "name" not in to  # 표본이 하나도 없는 키워드는 뺀다


def test_combine_keywords_rule_based():
    """생성 20개씩 → 파싱 → 키워드 조합으로 후보 추가(사용자 2026-11-04). 중복 키워드 없음, 기존 이름 제외, [대상]-[역할] 순서."""
    batches = [["name-echo", "name-probe", "sense-check"], ["name-probe", "meaning-echo", "word-check"],
               ["meaning-probe", "name-check", "sense-echo"]]
    got = nk.combine(batches, max_keywords=3, top=50, min_batches=2)
    names = [c["name"] for c in got]
    assert names and all(len(set(c["keywords"])) == len(c["keywords"]) for c in got)
    assert not set(names) & {n for b in batches for n in b}
    assert all(c["keywords"][0] in {"name", "meaning", "sense"} for c in got)  # 앞자리에 많이 온 키워드가 앞
    assert all(c["keywords"][-1] in {"echo", "probe", "check"} for c in got)
    assert "word" not in " ".join(names)  # 한 묶음에만 나온 키워드는 쓰지 않음
    assert got == sorted(got, key=lambda c: (len(c["keywords"]), -c["score"], c["name"]))  # 짧은 이름 먼저


def test_korean_names_parse_tokens_and_filter():
    import namecheck
    got = nk.parse_candidates("1. 첫눈 독자 — 처음 보고 뜻을 말함\n- 대조 평가자: 비교함\n2. first-reader — x")
    assert [c["name"] for c in got] == ["첫눈 독자", "대조 평가자", "first-reader"]
    assert nk.tokens("첫눈 독자") == ["첫눈", "독자"]
    kept, dropped = namecheck.filter_names(["첫눈 독자", "첫눈-독자", "가 나 다 라"], 3, " ")
    assert kept == ["첫눈 독자"] and len(dropped) == 2


def test_korean_generator_prompt_is_clean():
    import json
    import prompt_check
    prof = json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8"))
    brief = {"purpose": "이름만 보고 뜻을 말한다", "human_actions": [{"object": "뜻", "action": "말한다"}]}
    p = nk.gen_prompt(brief, prof, 20, "ko")
    assert "한국어 낱말" in p and prompt_check.check(p) == []


def test_dedupe_user_first_and_records():
    kept, dropped = nk.dedupe(["첫눈 독자"], ["첫눈 독자", "독자 첫눈", "읽는 이", "읽은 이", "name-mirror", "mirror-name",
                                          "처음 읽는 사람"])
    assert kept == ["첫눈 독자", "읽는 이", "name-mirror", "처음 읽는 사람"]
    assert {(d["name"], d["kept_as"], d["reason"]) for d in dropped} == {
        ("독자 첫눈", "첫눈 독자", "낱말이 같고 순서만 다름"), ("읽은 이", "읽는 이", "활용만 다름"),
        ("mirror-name", "name-mirror", "낱말이 같고 순서만 다름")}
