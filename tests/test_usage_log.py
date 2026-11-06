import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import plain_runner as pr  # noqa: E402
import run_naming as rn  # noqa: E402
from test_run_naming import BRIEF, PROFILE  # noqa: E402


def test_record_appends_and_summarizes(tmp_path):
    log = tmp_path / "usage.jsonl"
    with pr.usage(log, "첫눈 독자"):
        pr.record("claude", "haiku", 1.5, {"usage": {"input_tokens": 10, "output_tokens": 3}, "total_cost_usd": 0.01})
        pr.record("claude", "haiku", 0.5, {"usage": {"input_tokens": 5, "output_tokens": 2}})
    with pr.usage(log, "검색자"):
        pr.record("claude", "sonnet", 9.0)
    pr.record("claude", "x", 1.0)  # 기록 파일 밖: 쓰지 않는다
    s = pr.summarize(log)
    assert s["첫눈 독자"] == {"calls": 2, "seconds": 2.0, "input": 15, "output": 5, "cache_read": 0, "cost_usd": 0.01}
    assert s["검색자"]["calls"] == 1 and len(log.read_text(encoding="utf-8").splitlines()) == 3


def test_run_writes_usage_by_actor(tmp_path):
    def make(kind, model, art_dir):
        def call(names, timeout):
            pr.record(kind, model, 0.1)
            return {"items": [{"id": n["id"], "term": n["term"], "explanation": "이름 뜻"} for n in names]}
        return call
    out = rn.run(PROFILE, BRIEF, ["name-forecast"], tmp_path, rounds=1, backend_factory=make, check_network=False)
    rows = [json.loads(x) for x in (tmp_path / "usage.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows and {r["actor"] for r in rows} == {"첫눈 독자"} and out["usage"]["첫눈 독자"]["calls"] == len(rows)
    assert "주체별 호출 기록" in (tmp_path / "report.md").read_text(encoding="utf-8")
