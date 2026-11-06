import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import name_keywords as nk  # noqa: E402
import namecheck  # noqa: E402
import prompt_check  # noqa: E402
import search_words as sw  # noqa: E402

BRIEF = {"purpose": "이름을 처음 본 사람이 떠올리는 뜻을 모아 의도와 맞는지 본다",
         "human_actions": [{"subject": "사람", "verb": "고른다", "object": "이름"}]}
REPLY = """1. sense — 감각, 뜻 — https://dict.example/sense
2. meaning — 의미 — https://dict.example/meaning
3. tool — 도구 — https://dict.example/tool
잡담 한 줄"""


def state():
    return sw.search(BRIEF, lambda prompt: REPLY)


def test_search_parses_and_warns():
    s = state()
    assert [w["word"] for w in s["words"]] == ["sense", "meaning", "tool"]
    assert "tool" in s["words"][2]["warnings"] and not s["words"][0]["warnings"]


def test_search_prompt_has_no_dev_words():
    assert prompt_check.check(sw.search_prompt(BRIEF)) == []


def test_search_refuses_dirty_brief():
    with pytest.raises(prompt_check.PromptRejected):
        sw.search({**BRIEF, "purpose": "json 형식 검사"}, lambda p: REPLY)


def test_review_ok_lists_dropped():
    s = state()
    r = sw.review(s, [{"word": "sense", "keep": True}, {"word": "meaning", "keep": True},
                      {"word": "tool", "keep": False, "reason": "개발 용어 경고"}])
    assert r["status"] == "ok" and r["keep"] == ["meaning", "sense"]
    assert r["dropped"] == [{"word": "tool", "keep": False, "reason": "개발 용어 경고", "note": ""}]


def test_review_rejects_new_word_and_bad_reason_then_fix_only():
    s = state()
    r = sw.review(s, [{"word": "sense", "keep": True}, {"word": "checker", "keep": True},
                      {"word": "tool", "keep": False, "reason": "그냥"}])
    assert r["status"] == "rejected" and r["round"] == 1
    assert {e["word"] for e in r["errors"]} == {"checker", "tool"} and r["missing"] == ["meaning"]
    assert r["fix_only"] == ["checker", "meaning", "tool"]
    r = sw.review(s, [{"word": "meaning", "keep": True}, {"word": "tool", "keep": False, "reason": "너무 넓음"}])
    assert r["status"] == "ok"


def test_review_locks_accepted():
    s = state()
    sw.review(s, [{"word": "sense", "keep": True}])
    r = sw.review(s, [{"word": "sense", "keep": False, "reason": "너무 넓음"}])
    assert r["errors"] == [{"word": "sense", "error": "이미 받아들인 항목은 바꿀 수 없음"}]


def test_review_other_needs_note():
    r = sw.review(state(), [{"word": "tool", "keep": False, "reason": "기타"}])
    assert r["errors"][0]["error"] == "기타는 note 필수"


def test_review_stops_after_max_rounds():
    s = state()
    for _ in range(3):
        assert sw.review(s, [])["status"] == "rejected"
    assert sw.review(s, [])["status"] == "stopped"


def test_combine_uses_extra_words():
    batches = [["name-check", "word-guard"], ["name-guard", "word-check"]]
    names = {c["name"] for c in nk.combine(batches, extra=["sense"])}
    assert "name-sense" in names and "sense-check" in names
    assert not {c["name"] for c in nk.combine(batches)} & {"name-sense", "sense-check"}


def test_keywords_split_and_dedupe():
    assert sw.keywords(["brand name testing", "name research", "Name"]) == ["brand", "name", "testing", "research"]


@pytest.mark.parametrize("text", ["name testing", "tests", "tested", "a tester", "testers", "tools", "checker",
                                  "validating", "running", "the input data"])
def test_dictionary_catches_forms(text):  # 막음 또는 경고(tester·checker는 낱말 안 포함이라 경고)
    w = {"d": ["test", "tool", "check", "validate", "run", "input data"]}
    assert prompt_check.check(text, w, "all"), text


@pytest.mark.parametrize("text", ["testament", "contest", "stool", "rerun", "checkered flag"])
def test_dictionary_keeps_word_boundary(text):
    assert not prompt_check.check(text, {"d": ["test", "tool", "run", "check"]}), text


def test_cli_words_review_exit_codes(tmp_path):
    w = tmp_path / "words.json"
    w.write_text(json.dumps(state(), ensure_ascii=False), encoding="utf-8")
    d = tmp_path / "d.json"
    d.write_text(json.dumps({"decisions": [{"word": "sense", "keep": True}]}), encoding="utf-8")
    assert namecheck.main(["words-review", str(w), str(d), "--json"]) == 2
    d.write_text(json.dumps({"decisions": [{"word": "meaning", "keep": True},
                                           {"word": "tool", "keep": False, "reason": "개발 용어 경고"}]}), encoding="utf-8")
    assert namecheck.main(["words-review", str(w), str(d), "--json"]) == 0
    assert namecheck.main(["words-review", str(w), str(d), "--json"]) == 0  # 끝난 뒤에는 결과만 다시 보여 줌
