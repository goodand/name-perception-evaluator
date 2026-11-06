"""정리 세션 수학적 검증의 반례(2026-11-06). 고치기 전에는 실패해야 한다."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import prompt_check as pc  # noqa: E402
import prompt_slots as ps  # noqa: E402
import search_words as sw  # noqa: E402

HASH = "f7720e4771e2"  # simplemma 2.0.0


@pytest.mark.parametrize("text,word", [("", "e"), ("아무 말", "e"), ("cod", "code"), ("cods", "code"),
                                       ("modul", "module"), ("runes", "run"), ("testes", "test"), ("tooles", "tool")])
def test_false_positive(text, word):
    assert pc.check(text, {"d": [word]}) == []


@pytest.mark.parametrize("text,word", [("repositories", "repository"), ("libraries", "library"), ("ran", "run"),
                                       ("built", "build"), ("validating", "validate"), ("input-data", "input data"),
                                       ("input  data", "input data"), ("inputs data", "input data")])
def test_missed_now_blocked(text, word):  # 표제어 일치 → 막음
    assert [h["level"] for h in pc.check(text, {"d": [word]})] == ["block"], text


@pytest.mark.parametrize("text,word", [("pytest", "test"), ("unittest", "test"), ("codebase", "code"),
                                       ("deployment", "deploy"), ("tester", "test")])
def test_compounds_warn(text, word):  # 낱말 안 포함 → 경고만(LLM이 판단), 막지는 않음
    assert pc.check(text, {"d": [word]}) == [] and pc.warnings(text, {"d": [word]}), text


@pytest.mark.parametrize("text", ["validator", "validation", "deployment", "pytest", "codebase"])
def test_derivations_in_default_dictionary(text):  # 어떤 방법도 못 잡는 파생어는 사전에 올림
    assert pc.check(text), text


@pytest.mark.parametrize("text,word", [("contest", "test"), ("stool", "tool"), ("the runner-up", "run")])
def test_false_positive_is_only_warning(text, word):
    assert pc.check(text, {"d": [word]}) == [] and pc.warnings(text, {"d": [word]})


def test_lemma_repro_hash():  # simplemma==2.0.0 고정. 바뀌면 이 해시가 깨진다
    import hashlib
    ws = ["testing", "tests", "ran", "built", "repositories", "libraries", "validating", "runes", "cods", "modul",
          "contest", "testament", "data", "tools", "checked", "workflows"]
    got = [pc.lemma(w) for w in ws]
    assert got == [pc.lemma(w) for w in ws]
    assert hashlib.sha256("|".join(got).encode()).hexdigest()[:12] == HASH, got


@pytest.mark.parametrize("w", ["이름漢", "이름ㄱ", "이름é", "가α", "이름１", "이름漢.", "name)"])
def test_josa_non_hangul_end(w):
    with pytest.raises(ps.NoJosa):
        ps._josa(w, "이")


def _st():
    return sw.search({"purpose": "이름 뜻을 본다", "human_actions": []},
                     lambda p: "sense — 뜻 — https://a\nmeaning — 의미 — https://b")


def test_review_after_stopped_stays_stopped():
    s = _st()
    for _ in range(4):
        sw.review(s, [])
    assert sw.review(s, [{"word": "sense", "keep": True}, {"word": "meaning", "keep": True}])["status"] == "stopped"


def test_review_note_change_on_accepted_is_error():
    s = _st()
    sw.review(s, [{"word": "sense", "keep": False, "reason": "기타", "note": "가"}])
    r = sw.review(s, [{"word": "sense", "keep": False, "reason": "기타", "note": "나"}])
    assert r["errors"], "받아들인 note를 바꿨는데 오류가 없음"


def test_review_note_must_be_text():
    r = sw.review(_st(), [{"word": "sense", "keep": False, "reason": "기타", "note": 5}])
    assert r["errors"]


def test_josa_skips_only_trailing_punctuation():  # 끝 문장부호·공백은 건너뛴다(의도)
    assert ps._josa("이름 (가)", "이").endswith("가") and ps._josa("사용자.", "이")


def test_dictionary_rejects_symbols(tmp_path):
    f = tmp_path / "w.json"
    f.write_text('{"g": {"words": ["c++"]}}', encoding="utf-8")
    with pytest.raises(ValueError):
        pc.load(f)


def test_korean_spacing_is_known_limit():  # 알려진 한계: 한국어는 원문 부분 일치라 띄어 쓰면 못 잡는다
    assert pc.check("개발", {"g": ["개발"]}) and not pc.check("개 발", {"g": ["개발"]})
