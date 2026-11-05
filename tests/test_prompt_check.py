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


def test_run_reports_prompt_warnings(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "INSTR", cs.INSTR + " JSON으로 답하세요.")
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory([]),
                 check_network=False)
    assert any("json" in w for w in out["lint"])


def test_parse_plain_candidates():
    text = "1. name-echo — 이름이 어떻게 되돌아오는지\nsense-probe — 뜻을 더듬어 본다\n\n잡담\n- Name Mirror: 거울"
    got = nk.parse_candidates(text)
    assert [c["name"] for c in got] == ["name-echo", "sense-probe", "name-mirror"]
    assert got[1]["why"] == "뜻을 더듬어 본다"
