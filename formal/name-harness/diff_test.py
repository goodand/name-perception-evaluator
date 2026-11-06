"""차분 테스트: Lean 모델(lean/Diff.lean)과 파이썬 구현(scripts/check_terms.py·prompt_check.py)이 같은 입력에 같은 답을 내는가.

사용: python formal/name-harness/diff_test.py [lean/diff_out.txt]
  diff_out.txt는 `lake env lean --run Diff.lean > diff_out.txt`(Docker lean4 이미지)로 만든다.
Lean이 찍은 입력을 그대로 읽어(파싱) 파이썬에 넣고, Lean이 찍은 출력과 비교한다. 다르면 종료 코드 1.
신호어는 한 글자(a~j)라서 `norm(w) in text`와 집합 소속이 같다.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402
import prompt_check as pc  # noqa: E402

pc.lemma = lambda w: w  # 신호어가 한 글자(a~j)라 표제어를 그대로 두면 옛 모델(집합 소속)과 같다. 표제어 단계는 lemma_diff.py가 본다

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "lean/diff_out.txt"


def lean_list(s: str):
    """Lean의 `[a, b]`·`[(x, y)]`·`"a"`·`true` 표기를 파이썬 값으로."""
    s = s.replace("true", "True").replace("false", "False").replace("none", "None").replace("some ", "")
    s = re.sub(r"\(some (\"[^\"]*\")\)", r"\1", s)
    return eval(s, {"__builtins__": {}}, {"True": True, "False": False, "None": None})  # noqa: S307 — 자기 출력만 읽음


def kv(line: str, key: str) -> str:
    m = re.search(rf"\b{key}=(\[.*?\]|\(.*?\)|\S+?)(?= \w+=| =>|$)", line)
    return m.group(1)


def py_score(line: str) -> str:
    must = lean_list(kv(line, "must"))
    must_not = lean_list(kv(line, "mustNot"))
    mis = dict(lean_list(kv(line, "mis")))
    base = lean_list(kv(line, "base"))
    xs = lean_list(kv(line, "xs"))
    rule = {"id": "R", "term": "t", "must": must, "must_not": must_not, "misread_as": mis, "baseline": base}
    q = {**rule, "id": "Q", "term": "q"}
    h = ct.rule_hash(rule)
    recs, legacy_recs = [], []
    for text, contrast, stale, legacy in xs:
        item = [{"id": "R", "term": "t", "explanation": text}]
        if legacy:
            legacy_recs.append(item)  # 옛 형식: 봉투 없는 표본 배열(파일 단위로만 인식됨)
        else:
            recs.append({"format": "samples/v2", "role": "contrast" if contrast else "target", "status": "ok",
                         "backend": "x", "items": item, "rule_hashes": {"R": "0" * 12 if stale else h}})
    d = Path(__file__).parent / "lean"
    p, pl = d / ".diff_tmp.jsonl", d / ".diff_tmp_legacy.json"
    p.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in recs), encoding="utf-8")
    files = [p]
    if legacy_recs:
        pl.write_text(json.dumps(legacy_recs, ensure_ascii=False), encoding="utf-8")
        files.append(pl)
    try:
        s = ct.score({"R": rule}, files)["R"]
        ov = ct.overlap({"R": rule, "Q": q}, files)["R"]["with"]
    finally:
        p.unlink(missing_ok=True)
        pl.unlink(missing_ok=True)
    ov_s = "[(\"Q\", %d)]" % ov.get("Q", 0) if q["must"] else "[]"
    return f'pass={s["pass"]} n={s["n"]} misN={s["misread_n"]} exc={str(s["excluded"]).lower()} ov={ov_s}'


def py_choose(line: str) -> str:
    xs = lean_list(kv(line, "xs"))
    res = {f"c{i}": {"term": f"c{i}", "pass": p, "n": n, "misread_n": m, "excluded": e, "baseline": b}
           for i, (p, n, m, e, b) in enumerate(xs)}
    out = ct.choose(res)
    sel = f'some "{out["selected"]}"' if out["selected"] else "none"
    return f'sel={sel} fb={str(out["fallback"]).lower()}'


def py_prompt(line: str) -> str:
    g = lean_list(kv(line, "general")); l = lean_list(kv(line, "leaky")); t = lean_list(kv(line, "text"))
    hits = pc.check(" ".join(t), {"general": g, "leaky": l})
    return "[" + ", ".join(f'("{h["word"]}", "{h["dict"]}")' for h in hits) + "]"


def norm_lean(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def main() -> int:
    bad, n = [], 0
    lines, cur = [], ""
    for raw in OUT.read_text(encoding="utf-8").splitlines():  # repr가 긴 목록을 여러 줄로 찍으므로 이어 붙인다
        if re.match(r"^(score|choose|prompt) \d+ ", raw):
            if cur:
                lines.append(cur)
            cur = raw
        else:
            cur += " " + raw.strip()
    if cur:
        lines.append(cur)
    for line in lines:
        line = re.sub(r"\s+", " ", line)
        if " => " not in line:
            continue
        n += 1
        kind = line.split()[0]
        lean_out = norm_lean(line.split(" => ", 1)[1])
        py_out = {"score": py_score, "choose": py_choose, "prompt": py_prompt}[kind](line)
        if norm_lean(py_out) != lean_out:
            bad.append((line[:120], lean_out, py_out))
    for l, a, b in bad[:20]:
        print(f"DIFF {l}\n  lean: {a}\n  py:   {b}")
    print(f"비교 {n}건, 불일치 {len(bad)}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
