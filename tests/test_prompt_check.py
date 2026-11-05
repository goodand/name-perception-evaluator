"""지시문 검사(scripts/prompt_check.py) 명세 — 사용자 2026-11-05: 개발·SW 단어 사전(범용+자주 새는 단어)으로 경고, 금지는 아님.

생성자·답변자·평가자 지시문과 평문 입출력(plain_runner)이 개발 신호를 넣지 않는지 여기서 본다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import collect_samples as cs  # noqa: E402
import name_keywords as nk  # noqa: E402
import prompt_check as pc  # noqa: E402
import review_explanations as rv  # noqa: E402
import run_naming as rn  # noqa: E402
from test_run_naming import BRIEF, PROFILE, fake_factory  # noqa: E402


def test_check_finds_words_from_both_dicts():
    hits = pc.check("Return JSON for this software tool. 코드 이름.")
    got = {(h["word"], h["dict"]) for h in hits}
    assert ("json", "leaky") in got and ("software", "general") in got and ("코드", "general") in got
    assert not pc.check("이름 하나가 주어집니다. 뜻을 적어 주세요.")


def test_english_word_boundary():
    assert not pc.check("recode the codex")  # 'code'는 단어 경계 안에서만
    assert pc.check("the code is")


def test_harness_prompts_are_clean():
    prompts = {"답변자": cs.INSTR, "생성자": nk.GEN_PROMPT, "평가자": rv.INSTR.format(view=""),
               **{f"관점:{k}": v for k, v in PROFILE["perspectives"]["prompts"].items()}}
    assert pc.check_prompts(prompts) == []


def test_gpt_tail_is_flagged_and_only_for_gpt():
    assert pc.check(cs.GPT_TAIL)  # 동봉 실행기 제약으로 gpt에만 붙는 형식 요구는 경고로 보인다
    assert "json" not in cs.INSTR.lower()


def test_dirty_prompt_is_not_sent_without_fix(tmp_path, monkeypatch):
    """걸린 지시문은 응답자에게 가지 않는다: 고칠 수단이 없으면 수집 전에 멈춘다."""
    monkeypatch.setattr(cs, "INSTR", cs.INSTR + " JSON으로 답하세요.")
    sent = []
    try:
        rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory(sent), check_network=False)
        raise AssertionError("PromptRejected가 나야 함")
    except pc.PromptRejected as e:
        assert "json" in str(e)
    assert sent == []  # 한 번도 보내지 않음
    assert (tmp_path / "prompt_gate.json").is_file()


def test_gate_loop_revises_until_clean(tmp_path, monkeypatch):
    """걸리면 고침 → 다시 검사를 반복하고, 깨끗해진 지시문만 보낸다."""
    monkeypatch.setattr(cs, "INSTR", cs.INSTR + " JSON software 형식으로.")
    calls = []

    def reviser(text, words):  # 한 번에 한 단어씩만 지우는 고침(루프가 여러 번 도는지 본다)
        calls.append(words)
        w = words[0]
        return __import__("re").sub(w, "", text, flags=__import__("re").I)
    seen = []

    def make(kind, model, art_dir):
        def call(names, timeout):
            seen.append(cs.INSTR)
            return {"items": [{"id": n["id"], "term": n["term"], "explanation": "이름 뜻을 미리 확인하는 것"} for n in names]}
        return call
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=make, check_network=False,
                 prompt_reviser=reviser)
    assert len(calls) >= 2 and seen and all(not pc.check(s) for s in seen)
    assert any("프롬프트 거름" in w for w in out["lint"])
    assert "JSON" not in cs.INSTR or cs.INSTR.endswith("형식으로.")  # 실행 뒤 원래 값으로 복구(monkeypatch 값)


def test_gate_gives_up_after_max_rounds():
    try:
        pc.gate({"x": "code code"}, reviser=lambda t, w: t, max_rounds=2)
        raise AssertionError
    except pc.PromptRejected as e:
        assert "2번" in str(e)


def test_gate_keeps_slots_and_allows_recorded_exception():
    out, log = pc.gate({"t": "{view} 판단하세요", "gpt 꼬리": cs.GPT_TAIL}, reviser=None,
                       allow={"gpt 꼬리": ("json", "object")})
    assert out["t"] == "{view} 판단하세요" and log[-1]["allowed"] == ["json", "object"]
    try:
        pc.gate({"t": "{view} code"}, reviser=lambda t, w: "판단하세요", max_rounds=1)  # 자리표시를 지운 고침은 실패
        raise AssertionError
    except pc.PromptRejected as e:
        assert "자리표시" in str(e)


def test_parse_plain_candidates():
    text = "1. name-echo — 이름이 어떻게 되돌아오는지\nsense-probe — 뜻을 더듬어 본다\n\n잡담\n- Name Mirror: 거울"
    got = nk.parse_candidates(text)
    assert [c["name"] for c in got] == ["name-echo", "sense-probe", "name-mirror"]
    assert got[1]["why"] == "뜻을 더듬어 본다"
