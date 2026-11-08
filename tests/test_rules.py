"""규칙 엔진(scripts/rules.py) — 규칙마다 고정 ID·심각도·순수 함수, 결과는 같은 꼴의 진단(SkillMD 방식, 2026-11-06).

규칙마다 걸리는 입력과 안 걸리는 입력을 한 쌍씩 둔다. ID 목록은 외부 에이전트가 분기에 쓰므로 바뀌면 이 시험이 깨진다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import rules as R  # noqa: E402

BRIEF = json.loads((ROOT / "docs/harness/briefs/name-harness.json").read_text(encoding="utf-8"))
WORDS = {"general": ["test", "json"]}


def ids(diags):
    return [d.id for d in diags]


def test_rule_ids_are_stable():
    assert sorted(R.REGISTRY) == ["B001", "D001", "D002", "D003", "D004", "N001", "N002", "P001", "P002"]
    assert all(r.severity in ("error", "warn", "info") for r in R.REGISTRY.values())


def test_n001_name_format():
    assert ids(R.run({"names": ["name-mirror"], "sep": "-"}, ["N001"])) == []
    d = R.run({"names": ["Name Mirror"], "sep": "-"}, ["N001"])
    assert ids(d) == ["N001"] and d[0].severity == "error" and d[0].where == "Name Mirror"


def test_n001_korean_sep():
    assert ids(R.run({"names": ["첫눈 독자"], "sep": " "}, ["N001"])) == []
    assert ids(R.run({"names": ["첫눈-독자"], "sep": " "}, ["N001"])) == ["N001"]


def test_n002_keyword_count():
    ctx = {"names": ["a-b-c", "a-b-c-d"], "sep": "-", "max_keywords": 3}
    d = R.run(ctx, ["N002"])
    assert ids(d) == ["N002"] and d[0].where == "a-b-c-d"


def test_p001_block_and_p002_warn():
    ctx = {"prompts": {"답변자": "이 이름을 testing 해 주세요", "작명자": "contest 같은 이름"}, "words": WORDS}
    d = R.run(ctx, ["P001", "P002"])
    assert [(x.id, x.where) for x in d] == [("P001", "답변자"), ("P002", "작명자")]
    assert d[0].severity == "error" and d[1].severity == "warn"


def test_b001_brief_fields():
    assert ids(R.run({"brief": BRIEF}, ["B001"])) == []
    d = R.run({"brief": {**BRIEF, "purpose": ""}}, ["B001"])
    assert ids(d) == ["B001"] and "purpose" in d[0].message


def test_rule_skipped_without_its_input():
    assert R.run({"names": ["x"]}, ["B001", "P001"]) == []  # 해당 입력이 없으면 그 규칙은 돌지 않는다


def test_report_shape_and_exit_code():
    d = R.run({"names": ["Bad Name"], "sep": "-", "prompts": {"x": "contest"}, "words": WORDS})
    rep = R.report(d)
    assert rep["counts"] == {"error": 1, "warn": 1, "info": 0} and rep["exit"] == 1
    assert set(rep["diagnostics"][0]) == {"id", "severity", "message", "where", "file", "line"}
    assert R.report([d for d in d if d.severity == "warn"])["exit"] == 0


def test_cli_check(tmp_path):
    import namecheck
    f = tmp_path / "n.txt"
    f.write_text("name-mirror\nBad Name\n", encoding="utf-8")
    assert namecheck.main(["check", "--names", str(f), "--json"]) == 1
    f.write_text("name-mirror\n", encoding="utf-8")
    assert namecheck.main(["check", "--names", str(f), "--brief", str(ROOT / "docs/harness/briefs/name-harness.json"),
                           "--json"]) == 0
