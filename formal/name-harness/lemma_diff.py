"""두 단계 금지어 검사 차분 테스트: Lean 모델(lean/NameHarness/Lemma.lean)과 scripts/prompt_check.check(level="all").

사용: python formal/name-harness/lemma_diff.py lean/lemma_out.txt
  lemma_out.txt는 `lake env lean --run LemmaDiff.lean`(Docker lean4 이미지)으로 만든다.
- 표제어는 Lean과 같은 작은 표(LEM)로 바꿔 끼운다(simplemma 자체는 표제어 재현 해시가 따로 본다).
- 파이썬 쪽 글은 낱말 사이 구분자를 매번 다르게(공백·하이픈·쉼표·마침표·여러 칸·대문자) 만들어,
  3번 성질(공백·하이픈·문장부호만 다른 글은 결과가 같다)을 실제 토큰화로 함께 본다.
- 4번(한 단어 한 번)은 파이썬 결과에서 직접 센다. 순서는 비교하지 않는다(모델은 정렬을 뺐다).
종료 코드 1 = 불일치.
"""
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import prompt_check as pc  # noqa: E402

LEM = {"abs": "ab", "cabs": "cab", "tests": "test", "tested": "test"}
pc.lemma = lambda w: LEM.get(w, w)
SEPS = [" ", "-", ", ", "  ", ". ", " - ", "/", "\n", "_"]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "lean/lemma_out.txt"


def lean_val(s: str):
    return eval(s, {"__builtins__": {}})  # noqa: S307 — 자기 출력만 읽음


def main() -> int:
    rows = []
    for ln in OUT.read_text(encoding="utf-8").splitlines():  # repr가 긴 목록을 여러 줄로 찍으므로 이어 붙인다
        if re.match(r"^lem \d+ ", ln):
            rows.append(ln)
        elif rows:
            rows[-1] += " " + ln.strip()
    rng = random.Random(20261106)
    bad, n = [], 0
    for ln in rows:
        m = re.match(r"^lem (\d+) toks=(\[.*?\]) words=(\[.*?\]) => (\[.*\])\s*$", re.sub(r"\s+", " ", ln))
        toks, words, want = lean_val(m.group(2)), lean_val(m.group(3)), lean_val(m.group(4))
        for _ in range(3):  # 같은 낱말 목록, 구분자만 다른 글 세 개
            text = "".join(t.upper() if rng.random() < 0.2 else t for t in
                           (x for i, tok in enumerate(toks) for x in ((rng.choice(SEPS) if i else rng.choice(["", " ", "("])), tok)))
            text += rng.choice(["", ".", "!", " )"])
            got = pc.check(text, {"d": words}, "all")
            n += 1
            names = [h["word"] for h in got]
            if len(names) != len(set(names)):
                bad.append((m.group(1), text, "중복", names))
            if sorted((h["word"], h["level"]) for h in got) != sorted(map(tuple, want)):
                bad.append((m.group(1), text, want, [(h["word"], h["level"]) for h in got]))
    for i, t, a, b in bad[:15]:
        print(f"DIFF case {i} text={t!r}\n  lean: {a}\n  py:   {b}")
    print(f"두 단계 검사 비교 {n}건, 불일치 {len(bad)}건")
    return 1 if bad or not n else 0


if __name__ == "__main__":
    sys.exit(main())
