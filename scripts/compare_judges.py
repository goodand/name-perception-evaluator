"""판정기 기존안 비교 — 수정 프로토콜의 '기존안과 후보를 같은 입력으로 비교, 동점이면 기존 유지' 단계 (하네스 v2.2).

사용: python scripts/compare_judges.py <기존안: git 커밋 또는 check_terms.py 경로> <규칙>::<표본,표본…> [<규칙>::<표본…> …]
- 같은 (규칙, 표본) 쌍을 기존 판정기와 현재 판정기(scripts/check_terms.py)에 넣고 이름별 판정 줄을 비교한다.
- 줄바꿈(CR) 차이는 무시. 현재 판정기 출력의 빈 줄 뒤(선택:·재실험 표 등)는 덧붙은 출력이라 비교에서 뺀다.
- 판정식을 바꿨다면 차이가 나야 정상이다: 그때는 JUDGE_VERSION을 올리고 차이 줄을 직접 읽어 의도한 변화인지 확인한다.
절차: docs/harness/NAMING_GUIDE.md '하네스를 고칠 때', skills/modification-protocol/SKILL.md
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[1]
NEW = ROOT / "scripts/check_terms.py"


def old_judge_from_git(ref: str) -> Path:
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:scripts/check_terms.py"], capture_output=True,
                         text=True, encoding="utf-8", check=True).stdout
    d = Path(tempfile.mkdtemp(prefix="judge_old_"))
    p = d / "check_terms.py"
    p.write_text(src, encoding="utf-8")
    return p


def _lines(judge: Path, rules: Path, samples: list[Path]) -> list[str]:
    out = subprocess.run([sys.executable, str(judge), "--rules", str(rules), "--samples", *map(str, samples)],
                         capture_output=True, text=True, encoding="utf-8").stdout.replace("\r", "")
    return out.split("\n\n", 1)[0].strip("\n").split("\n") if out.strip() else []


def compare(old: Path, new: Path, pairs: list) -> dict:
    res = {"pairs": [], "total_lines": 0, "diff_lines": 0}
    for rules, samples in pairs:
        a, b = _lines(old, rules, samples), _lines(new, rules, samples)
        diff = [(x, y) for x, y in zip(a, b) if x != y] + [(x, None) for x in a[len(b):]] + [(None, y) for y in b[len(a):]]
        res["pairs"].append({"rules": str(rules), "lines": len(a), "diff": diff})
        res["total_lines"] += len(a)
        res["diff_lines"] += len(diff)
    return res


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    old = Path(a[0]) if Path(a[0]).is_file() else old_judge_from_git(a[0])
    pairs = []
    for spec in a[1:]:
        r, s = spec.split("::", 1)
        pairs.append((Path(r), [Path(x) for x in s.split(",")]))
    out = compare(old, NEW, pairs)
    print("규칙 파일 | 판정 줄 | 다른 줄")
    for p in out["pairs"]:
        print(f'{Path(p["rules"]).name} | {p["lines"]} | {len(p["diff"])}')
        for x, y in p["diff"][:5]:
            print(f"  기존: {x}\n  새것: {y}")
    print(f'합계: 판정 줄 {out["total_lines"]}, 다른 줄 {out["diff_lines"]}')


if __name__ == "__main__":
    main()
