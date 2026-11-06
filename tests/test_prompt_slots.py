import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import prompt_slots as p  # noqa: E402

pytest.importorskip("kiwipiepy")
W = {"general": ["user", "tool"]}


@pytest.mark.parametrize("w,j,want", [
    ("사용자", "이", "사용자가"), ("한 줄", "으로", "한 줄로"), ("일반 사용자", "은", "일반 사용자는"), ("이름", "와", "이름과"),
    ("1~2문장", "으로", "1~2문장으로"), ("B팀", "이", "B팀이"), ("조건", "을", "조건을")])
def test_josa_korean(w, j, want):
    assert p._josa(w, j) == want


@pytest.mark.parametrize("w", ["name", "book", "LLM", "sense-match", "3", "100"])
def test_josa_english_and_numbers_refused(w):
    with pytest.raises(p.NoJosa):
        p._josa(w, "이")


def test_english_ok_without_josa():
    assert p.render("이름: {이름}", {"이름": "name-mirror"}) == "이름: name-mirror"


def test_gate_refills_only_hit_slot():
    calls = []

    def filler(req):
        calls.append(req)
        assert [h["slot"] for h in req["hits"]] == ["독자"]
        return {"독자": "처음 보는 사람"}
    text, log = p.gate("{독자|이} {길이|으로} 적는다", {"독자": "end user", "길이": "한 줄"}, filler, words=W)
    assert text == "처음 보는 사람이 한 줄로 적는다"
    assert len(calls) == 1 and log[-1]["hits"] == []


def test_gate_rejects_touching_other_slot():
    with pytest.raises(p.SlotRejected, match="걸리지 않은"):
        p.gate("{독자|이} {길이}", {"독자": "user", "길이": "한 줄"}, lambda r: {"독자": "사람", "길이": "두 줄"}, words=W)


def test_gate_rejects_repeat_value():
    with pytest.raises(p.SlotRejected, match="다시 냄"):
        p.gate("{독자|이}", {"독자": "user"}, lambda r: {"독자": "user"}, words=W)


def test_gate_stops_after_max_rounds():
    vals = iter(["tool 사람", "user 팀원", "tool 독자", "user 손님"])
    with pytest.raises(p.SlotRejected, match="3번"):
        p.gate("{독자|이}", {"독자": "user"}, lambda r: {"독자": next(vals)}, words=W)


def test_gate_english_in_josa_slot_is_refilled():
    text, _ = p.gate("{독자|이} 본다", {"독자": "reader"}, lambda r: {"독자": "독자"}, words=W)
    assert text == "독자가 본다"


def test_template_hash_changes():
    assert p.template_hash("{a}") != p.template_hash("{a} ")


def test_kiwi_same_output_across_instances():
    from kiwipiepy import Kiwi
    vals = [("사용자", "이"), ("한 줄", "으로"), ("이름", "와"), ("조건", "을"), ("처음 보는 사람", "의")]
    a = [p._josa(w, j) for w, j in vals]
    p._KIWI = Kiwi()  # 새 인스턴스로 다시
    assert [p._josa(w, j) for w, j in vals] == a


def test_answerer_template_default_equals_current_instr():
    import collect_samples as cs
    t = p.load()
    assert p.render(t["templates"]["답변자"], t["defaults"]["답변자"]) == cs.INSTR


def _make(seen):
    def make(kind, model, art_dir):
        def call(names, timeout):
            seen.append(__import__("collect_samples").INSTR)
            return {"items": [{"id": n["id"], "term": n["term"], "explanation": "이름 뜻"} for n in names]}
        return call
    return make


def test_run_with_slots_renders_and_rejects(tmp_path):
    import run_naming as rn
    from test_run_naming import BRIEF, PROFILE
    seen = []
    rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path / "a", rounds=1, backend_factory=_make(seen),
           check_network=False, slots={"독자": "팀원"})
    assert seen and "처음 본 팀원이" in seen[0] and (tmp_path / "a/slot_gate.json").exists()
    with pytest.raises(p.SlotRejected):
        rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path / "b", rounds=1, backend_factory=_make([]),
               check_network=False, slots={"독자": "end user"})


def test_gpt_gets_persona(monkeypatch, tmp_path):
    import collect_samples as cs
    got = []

    class A:
        @staticmethod
        def run_agent(payload, instr, *rest):
            got.append(instr)
            return {"items": []}
    monkeypatch.setattr(cs, "load_adapters", lambda: A)
    cs.make_backend("gpt", "gpt-6-luna", tmp_path)([{"id": "C01", "term": "x"}], 10)
    assert got[0].startswith(cs.GPT_PERSONA) and got[0].endswith(cs.GPT_TAIL)
