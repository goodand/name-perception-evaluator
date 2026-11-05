"""에이전트용 CLI(scripts/namecheck.py) 명세.

사용자(2026-11-04): 스킬보다 먼저 'tool using agent CLI tool'. 반복·선택지 적은 일은 스크립트(모델 무관 재현).
빈칸 채우기 + 구조화 출력: 빈칸에 들어갈 값의 자료형·형식을 강제한다(허용 값 목록은 최적화 뒤에 정한다).
삼중항 글쓰기: 사람 행동은 {actor, action, object}.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import namecheck as nc  # noqa: E402
import name_keywords as nk  # noqa: E402

BRIEF = ROOT / "docs/harness/briefs/name-harness.json"


def cli(*args):
    p = subprocess.run([sys.executable, str(ROOT / "scripts/namecheck.py"), *args], capture_output=True, text=True,
                       encoding="utf-8")
    return p.returncode, p.stdout, p.stderr


# 브리프 형식: 삼중항
def test_brief_valid_example():
    assert nc.check_brief(json.loads(BRIEF.read_text(encoding="utf-8"))) == []


def test_brief_triples_required():
    b = json.loads(BRIEF.read_text(encoding="utf-8"))
    bad = {**b, "human_actions": [["이름", "정한다"]]}  # 주체 없는 쌍
    assert any("actor" in e for e in nc.check_brief(bad))
    for acts in ([], [{"actor": "사람", "action": "정한다", "object": "이름"}] * 4,
                 [{"actor": "사람", "action": "", "object": "이름"}]):
        assert nc.check_brief({**b, "human_actions": acts}), acts


def test_brief_required_fields_and_types():
    errs = nc.check_brief({"purpose": "", "audience": "alien"})
    for f in ("purpose", "human_actions", "audience", "distinct_from", "must"):
        assert any(f in e for e in errs), f


def test_human_actions_as_pairs_for_prompt():
    """생성 프롬프트에는 '대상을 행동한다'만 넣는다(주체는 늘 사람)."""
    b = json.loads(BRIEF.read_text(encoding="utf-8"))
    assert nk.GEN_PROMPT == nk.gen_prompt(b, json.loads((ROOT / "docs/harness/naming_profile.json").read_text(encoding="utf-8")))


# 생성 이름 형식: 패턴으로 거르고 사유를 남긴다
def test_name_pattern_filter():
    kept, dropped = nc.filter_names(["name-echo", "Name Echo", "a-b-c-d", "name_echo", "이름-확인", "x--y", "ok"], 3)
    assert kept == ["name-echo", "ok"]
    reasons = dict(dropped)
    assert "키워드 4개" in reasons["a-b-c-d"] and "형식" in reasons["Name Echo"] and "형식" in reasons["이름-확인"]


# CLI: 에이전트는 --json, 종료 코드로 성공/실패
def test_cli_brief_check_json():
    code, out, _ = cli("brief-check", str(BRIEF), "--json")
    assert code == 0 and json.loads(out) == {"ok": True, "errors": []}


def test_cli_brief_check_fails(tmp_path):
    p = tmp_path / "b.json"
    p.write_text(json.dumps({"purpose": ""}, ensure_ascii=False), encoding="utf-8")
    code, out, _ = cli("brief-check", str(p), "--json")
    assert code == 1 and json.loads(out)["ok"] is False


def test_cli_lint_json(tmp_path):
    code, out, _ = cli("lint", str(BRIEF), "name-echo,decision-tabular-engine,a-b-c-d", "--json")
    r = json.loads(out)
    assert code == 0 and r["dropped"] == [["a-b-c-d", "키워드 4개(최대 3)"]]
    assert any("decision" in w for w in r["warnings"]) and any("engine" in w for w in r["warnings"])


def test_cli_help_lists_commands():
    code, out, _ = cli("--help")
    for c in ("brief-check", "generate", "lint", "availability", "run", "judge", "compare", "stats", "risk"):
        assert c in out, c


def test_doctor_reports_backends():
    code, out, _ = cli("doctor", "--json")
    rep = json.loads(out)
    assert code == 0 and {"claude", "gpt", "qwen"} <= set(rep)
    assert all("ok" in v and "detail" in v for v in rep.values())


def test_ensure_lmstudio_starts_server_and_loads(monkeypatch):
    """LM Studio 서버가 꺼져 있으면 켜고 모델을 올린다(사용자 2026-11-05: '꺼져 있으면 키면 되잖아')."""
    state = {"up": False, "loaded": [], "cmds": []}
    monkeypatch.setattr(nc, "_lms_models", lambda: list(state["loaded"]) if state["up"] else None)

    def fake_lms(*args):
        state["cmds"].append(args)
        if args[:2] == ("server", "start"):
            state["up"] = True
        if args[0] == "load":
            state["loaded"].append(args[1])
        return 0
    monkeypatch.setattr(nc, "_lms", fake_lms)
    assert nc.ensure_lmstudio(["qwen/qwen3.8-27b"]) == []
    assert ("server", "start") in state["cmds"] and any(c[0] == "load" for c in state["cmds"])


def test_ensure_lmstudio_reports_when_lms_missing(monkeypatch):
    monkeypatch.setattr(nc, "_lms_models", lambda: None)
    monkeypatch.setattr(nc, "_lms", lambda *a: None)  # lms CLI 없음
    errs = nc.ensure_lmstudio(["x"])
    assert errs and "lms" in errs[0]


def test_no_local_blocks_local_answerers(monkeypatch):
    """--no-local: 로컬 LLM 답변자를 막고 LM Studio를 켜지 않는다(사용자 2026-11-05: GPU를 다른 세션이 씀)."""
    called = []
    monkeypatch.setattr(nc, "ensure_lmstudio", lambda m: called.append(m) or [])
    code = nc.main(["run", str(BRIEF), "name-echo", "unused_out", "--no-network", "--no-local",
                    "--answerers", "claude:haiku,qwen:qwen/qwen3.8-27b"])
    assert code == 1 and called == []


def test_brief_template_new_and_unfilled(tmp_path):
    """용어 정의 빈칸 틀(사용자 2026-11-05): brief-new로 복사, 빈칸 <…>가 남으면 brief-check 실패."""
    out = tmp_path / "b.json"
    assert nc.main(["brief-new", str(out)]) == 0 and nc.main(["brief-new", str(out)]) == 1  # 덮어쓰지 않음
    errs = nc.check_brief(json.loads(out.read_text(encoding="utf-8")))
    assert any("빈칸 그대로" in e for e in errs)


def test_brief_purpose_from_definition_pattern():
    b = {"definition": {"pattern": "사람이 {xx}끼리 대조해 {yy}를 파악하고 {zz}를 결정한다", "xx": "표", "yy": "차이",
                        "zz": "남길 조건"}, "purpose": "", "human_actions": [{"actor": "사람", "action": "대조한다", "object": "표"}],
         "audience": "end-user", "distinct_from": {"엑셀 비교": "c"}, "must": [{"label": "표", "any": ["표"]}]}
    assert nc.fill_purpose(b)["purpose"] == "사람이 표끼리 대조해 차이를 파악하고 남길 조건를 결정한다"  # 틀은 조사를 안 바꾼다: 사용자가 pattern 문장을 직접 쓴다
    assert nc.check_brief(b) == []
