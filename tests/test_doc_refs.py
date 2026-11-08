"""죽은 참조 검사(scripts/doc_refs.py) — 문서가 가리키는 명령·옵션·파일·함수가 지금 코드에 있는지(dify check-glossary-keys 방식).

규칙: D001 명령, D002 옵션, D003 경로, D004 함수·속성. 역따옴표 안만 본다. 코드 블록 밖·안 모두 본다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import doc_refs as dr  # noqa: E402
import rules as R  # noqa: E402


def refs(text):
    return [(d.id, d.where) for d in R.run({"docs": {"x.md": text}, "repo": ROOT}, ["D001", "D002", "D003", "D004"])]


def test_live_refs_pass():
    assert refs("`namecheck run` `--slots` `scripts/prompt_slots.py` `prompt_check.check()` `dedupe()`") == []


def test_dead_command_option_path_symbol():
    got = refs("`namecheck frobnicate` `--prompt-reviser` `scripts/nope.py` `prompt_check.claude_reviser()` `gone_fn()`")
    assert got == [("D001", "frobnicate"), ("D002", "--prompt-reviser"), ("D003", "scripts/nope.py"),
                   ("D004", "prompt_check.claude_reviser"), ("D004", "gone_fn")]


def test_line_numbers_and_placeholders():
    d = R.run({"docs": {"a.md": "첫 줄\n`<out>/report.md` `docs/harness/briefs/<주제>.json`\n`--nope`"}, "repo": ROOT},
              ["D002", "D003"])
    assert [(x.id, x.line) for x in d] == [("D002", 3)]  # 자리표시가 있는 경로는 건너뛴다


def test_other_tools_options_ignored():
    assert refs("`uv pip install --system-certs -r requirements.txt` `curl --retry 5`") == []


def test_extract_kinds():
    k = dr.extract("`python scripts/namecheck.py combine --top 3` `run_naming.run`")
    assert ("command", "combine") in k and ("option", "--top") in k and ("path", "scripts/namecheck.py") in k
    assert ("symbol", "run_naming.run") in k


def test_current_docs_have_no_dead_refs():
    docs = {p.name: p.read_text(encoding="utf-8") for p in
            [ROOT / "README.md", ROOT / "docs/harness/NAMING_GUIDE.md", ROOT / "docs/harness/REPO_DEFINITION.md"]}
    dead = R.run({"docs": docs, "repo": ROOT}, ["D001", "D002", "D003", "D004"])
    assert dead == [], [(d.file, d.line, d.where) for d in dead]
