"""collect_samples.py 명세 (docs/harness/name_harness_v2.md v2.1)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402
import collect_samples as cs  # noqa: E402

RULES = {f"R0{i}": {"id": f"R0{i}", "term": f"name-{i}", "must": [["x"]], "must_not": [], "contrasts": []} for i in (1, 2, 3)}
RULES["R01"]["contrasts"] = ["auto-merge-tool"]


class Fake:
    def __init__(self, fail_on=None, exc=None, shape="items"):
        self.calls, self.fail_on, self.exc, self.shape = [], fail_on, exc, shape

    def __call__(self, names, timeout):
        self.calls.append(names)
        if self.exc and names[0]["term"] == self.fail_on:
            raise self.exc
        items = [{"id": n["id"], "term": n["term"], "explanation": "x 설명"} for n in names]
        return {"items": items} if self.shape == "items" else {"status": "succeeded", "output": None}


def lines(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def run(tmp_path, fake, **kw):
    out = tmp_path / "s.jsonl"
    cs.collect(fake, RULES, rules_file="r.yaml", k=2, out=out, model="fake-1", backend="fake", timeout=5, **kw)
    return out


# validate
def test_validate():
    names = [{"id": "R01", "term": "name-1"}]
    ok = [{"id": "R01", "term": "name-1", "explanation": "e"}]
    assert cs.validate({"items": ok}, names)[0] == "ok"
    for raw in ([], {"items": []}, {"status": "succeeded", "output": None}, {"status": "failed", "output": None},
                {"items": [dict(ok[0], explanation=" ")]}, {"items": [dict(ok[0], term="other")]},
                {"items": [dict(ok[0], id="R09")]}, {"items": ok + ok}):
        assert cs.validate(raw, names)[0] == "failed", raw


# solo 기본: 이름 하나당 호출, 대조 이름 포함, 순서 뒤집기 없음
def test_solo_default(tmp_path):
    fake = Fake()
    out = run(tmp_path, fake)
    assert all(len(c) == 1 for c in fake.calls)
    assert len(fake.calls) == 2 * 4  # 이름 3 + 대조 1, 2회차
    ls = lines(out)
    assert {x["role"] for x in ls} == {"target", "contrast"}
    c = next(x for x in ls if x["role"] == "contrast")
    assert c["items"][0]["id"] == "R01" and c["items"][0]["term"] == "auto-merge-tool"
    x = ls[0]
    assert x["format"] == "samples/v2" and x["mode"] == "solo" and x["model"] == "fake-1"
    assert x["instr_sha"] == cs.instr_sha() and x["rule_hashes"]["R01"] == ct.rule_hash(RULES["R01"])


def test_list_mode_reverses(tmp_path):
    fake = Fake()
    run(tmp_path, fake, mode="list")
    targets = [c for c in fake.calls if len(c) == 3]
    assert [n["id"] for n in targets[0]] == ["R01", "R02", "R03"]
    assert [n["id"] for n in targets[1]] == ["R03", "R02", "R01"]


# 예외는 실패 표본으로, 나머지는 계속
def test_timeout_recorded_and_continues(tmp_path):
    out = run(tmp_path, Fake(fail_on="name-2", exc=TimeoutError()))
    ls = lines(out)
    st = [(x["items"][0]["term"] if x["items"] else x["names"][0]["term"], x["status"]) for x in ls]
    assert ("name-2", "timed_out") in st and ("name-3", "ok") in st


def test_other_exception_failed(tmp_path):
    out = run(tmp_path, Fake(fail_on="name-1", exc=ValueError("no [")))
    assert any(x["status"] == "failed" and "no [" in x["error"] for x in lines(out))


def test_adapter_none_output_failed(tmp_path):
    out = run(tmp_path, Fake(shape="none"))
    assert {x["status"] for x in lines(out)} == {"failed"}


# 재개: 이미 받은 (모델, 이름, 회차)는 건너뜀, 실패는 다시 시도
def test_resume(tmp_path):
    run(tmp_path, Fake(fail_on="name-2", exc=TimeoutError()))
    fake = Fake()
    out = run(tmp_path, fake)
    assert [c[0]["term"] for c in fake.calls] == ["name-2", "name-2"]
    ok = [x for x in lines(out) if x["status"] == "ok"]
    assert len(ok) == 8


# 판정기와 연결
def test_score_reads_collected(tmp_path):
    out = run(tmp_path, Fake())
    s = ct.score(RULES, [out])
    assert (s["R01"]["pass"], s["R01"]["n"]) == (2, 2)
    assert s["R01"]["contrast"] == {"auto-merge-tool": [2, 2]}
