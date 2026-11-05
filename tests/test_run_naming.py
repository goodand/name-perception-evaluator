"""한 번에 돌리는 명명 검증(scripts/run_naming.py) 명세 — Claude 모델만으로 동작(사용자 2026-11-04).

프로필(주제 무관 기준) + 브리프(주제별 평가자 맥락) + 후보 목록 → 규칙 생성 → 사전 검사 → 수집(모델별 폴더,
독자가 사람이면 사람 관점 추가) → 오독 게이트 판정 → 선택. 테스트는 가짜 답변자로 네트워크·로그인 없이 돈다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_naming as rn  # noqa: E402

PROFILE = json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8"))
BRIEF = json.loads((ROOT / "docs/harness/briefs/name-harness.json").read_text(encoding="utf-8"))

ANSWERS = {  # 이름 → 답변자가 내놓는 설명(가짜)
    "name-forecast": "새 이름을 처음 보는 사람이 어떤 뜻으로 받아들일지 미리 확인하는 도구로 보입니다.",
    "name-linter-x": "변수명과 함수명이 명명 규칙을 따르는지 검사하는 린터로 보입니다.",
    "random-name-generator": "무작위 이름을 만드는 도구입니다.",
    "naming-convention-linter": "코드의 명명 규칙 준수를 검사합니다.",
}


def fake_factory(sent):
    def make(kind, model, art_dir):
        def call(names, timeout):
            sent.append({"model": model, "names": names})
            return {"items": [{"id": n["id"], "term": n["term"], "explanation": ANSWERS[n["term"]]} for n in names]}
        return call
    return make


def test_build_rules_from_brief():
    rules = rn.build_rules(BRIEF, ["name-forecast", "name-linter-x"])
    assert list(rules) == ["C01", "C02"]
    r = rules["C01"]
    assert r["term"] == "name-forecast" and r["misread_as"] == BRIEF["misread_as"] and r["purpose"] == BRIEF["purpose"]
    assert r["contrasts"] == BRIEF["contrasts"] and "contrasts" not in rules["C02"]  # 대조는 한 번만 수집


def test_perspectives_follow_audience():
    assert rn.perspectives({"audience": "developer"}, PROFILE) == ["developer"]
    assert rn.perspectives({"audience": "end-user"}, PROFILE) == ["developer", "ux", "end_user"]
    assert rn.perspectives({"audience": "developer"}, PROFILE, force_human=True) == ["developer", "ux", "end_user"]


def test_run_end_to_end_offline(tmp_path):
    sent = []
    out = rn.run(PROFILE, BRIEF, ["name-forecast", "name-linter-x"], tmp_path, rounds=2,
                 backend_factory=fake_factory(sent), check_network=False)
    assert out["selected"] == "name-forecast" and out["fallback"] is False
    s = out["scores"]
    assert s["C02"]["excluded"] is True and s["C02"]["misread_n"] == s["C02"]["n"]
    assert s["C01"]["n"] == 2 * 2  # 모델 2개(sonnet, haiku) × 2회, 관점 developer만
    # 모델별 폴더 분리
    assert (tmp_path / "sonnet").is_dir() and (tmp_path / "haiku").is_dir()
    assert {x["model"] for x in sent} == {"sonnet", "haiku"}
    # 결과 파일
    assert json.loads((tmp_path / "rules.json").read_text(encoding="utf-8"))["terms"]
    assert "name-forecast" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_answerer_gets_only_names(tmp_path):
    sent = []
    rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory(sent), check_network=False)
    blob = json.dumps(sent, ensure_ascii=False)
    for leak in (BRIEF["purpose"], "고른다", "네이밍 컨벤션 린터", "명명 규칙", BRIEF["role"]):
        assert leak not in blob, leak
    assert all(set(n) == {"id", "term"} for x in sent for n in x["names"])


def test_human_audience_adds_perspectives(tmp_path):
    sent = []
    out = rn.run(PROFILE, {**BRIEF, "audience": "end-user"}, ["name-forecast"], tmp_path, rounds=1,
                 backend_factory=fake_factory(sent), check_network=False)
    assert out["scores"]["C01"]["n"] == 2 * 3  # 모델 2 × 관점 3
    assert len({x["model"] for x in sent}) == 2


def test_fallback_when_all_excluded(tmp_path):
    out = rn.run(PROFILE, BRIEF, ["name-linter-x"], tmp_path, rounds=1, backend_factory=fake_factory([]),
                 check_network=False)
    assert out["selected"] == "name-linter-x" and out["fallback"] is True


def test_low_pass_selection_warned(tmp_path):
    """다른 후보가 모두 제외되면 통과 0인 이름도 선택된다(2026-11-04 실측: name-echo 0/2) → 경고."""
    ans = {**ANSWERS, "name-forecast": "날씨를 예측하는 도구입니다."}  # 오독은 아니지만 통과도 못 함

    def make(kind, model, art_dir):
        return lambda names, timeout: {"items": [{"id": n["id"], "term": n["term"], "explanation": ans[n["term"]]}
                                                 for n in names]}
    out = rn.run(PROFILE, BRIEF, ["name-forecast", "name-linter-x"], tmp_path, rounds=1, backend_factory=make,
                 check_network=False)
    assert out["selected"] == "name-forecast" and out["warnings"]
    assert "통과율" in out["warnings"][0] and "경고" in (tmp_path / "report.md").read_text(encoding="utf-8")


def test_good_selection_no_warning(tmp_path):
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory([]),
                 check_network=False)
    assert out["warnings"] == []


def test_lint_reported(tmp_path):
    out = rn.run(PROFILE, BRIEF, ["name-forecast", "name-linter-x"], tmp_path, rounds=1,
                 backend_factory=fake_factory([]), check_network=False)
    assert any("linter" in w for w in out["lint"])


def test_answerers_override(tmp_path):
    """gpt·로컬 LLM도 시도: --answerers로 프로필 기본(Sonnet·Haiku)을 바꾼다. 모델별 폴더는 '/'를 바꿔 만든다."""
    sent = []
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=fake_factory(sent),
                 check_network=False, answerers=[("gpt", "gpt-6-luna"), ("qwen", "qwen/qwen3.8-27b")])
    assert {x["model"] for x in sent} == {"gpt-6-luna", "qwen/qwen3.8-27b"}
    assert (tmp_path / "gpt-6-luna").is_dir() and (tmp_path / "qwen_qwen3.8-27b").is_dir()
    assert out["scores"]["C01"]["n"] == 2


def test_parse_answerers():
    assert rn.parse_answerers("claude:haiku,qwen:qwen/qwen3.8-27b") == [("claude", "haiku"), ("qwen", "qwen/qwen3.8-27b")]


def test_answerer_prompts_have_no_software_words():
    """답변자 지시문에 개발·SW 단어를 넣지 않는다 — '명시하지 않는다'가 아니라 단어 자체를 뺀다(사용자 2026-11-05).
    'software repository'·'developer' 같은 말이 들어가면 답변이 그쪽으로 끌려간다."""
    import collect_samples as cs
    banned = ("software", "repositor", "code", "developer", "program", "tool", "개발", "소프트웨어", "코드")
    import name_keywords as nk
    for text in (cs.INSTR, nk.GEN_PROMPT, *PROFILE["perspectives"]["prompts"].values()):  # 생성자 프롬프트도
        assert not [w for w in banned if w in text.lower()], text
