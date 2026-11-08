"""죽은 참조 검사: 문서의 역따옴표 안 명령·옵션·경로·함수가 지금 코드에 있는지(dify check-glossary-keys 방식, 2026-11-06).

규칙은 rules.py에 D001~D004로 등록된다(ctx: docs {파일 이름: 글}, repo 경로).
  D001 namecheck 명령   D002 --옵션   D003 저장소 안 경로   D004 모듈.이름 또는 이름() 꼴의 함수·속성
자리표시(<…>, {…}, *)가 든 경로는 건너뛴다. 결정 기록·옛 기록처럼 지운 것을 일부러 말하는 문서는 넣지 않는다.
"""
import ast
import re
from functools import lru_cache
from pathlib import Path

TICK = re.compile(r"`([^`\n]+)`")
CMD = re.compile(r"(?:namecheck(?:\.py)?)\s+([a-z][a-z-]*)")
OPT = re.compile(r"(?<![\w-])(--[a-z][a-z0-9-]*)")
PATH = re.compile(r"(?<![\w/.-])((?:scripts|docs|tests|formal|skills)/[\w./<>{}*가-힣-]+)")
SYM = re.compile(r"(?<![\w./-])([a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)?)\(\)|(?<![\w./-])([a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*)(?![\w./])")
PLACEHOLDER = re.compile(r"[<>{}*]")


def extract(text: str) -> list[tuple[str, str]]:
    out = []
    for tick in TICK.findall(text):
        out += [("command", m) for m in CMD.findall(tick)]
        if re.search(r"namecheck|scripts/", tick) or OPT.fullmatch(tick.strip()):  # 남의 도구 옵션(uv --system-certs 등)은 보지 않음
            out += [("option", m) for m in OPT.findall(tick)]
        out += [("path", m.rstrip(".,")) for m in PATH.findall(tick)]
        for a, b in SYM.findall(tick):
            s = a or b
            if s and not s.endswith((".py", ".json", ".md", ".txt", ".jsonl", ".sh", ".ini", ".lean")):
                out.append(("symbol", s))
    return out


@lru_cache(maxsize=None)
def _index(repo: str):
    root = Path(repo)
    src = {p.stem: p.read_text(encoding="utf-8") for p in (root / "scripts").glob("*.py")}
    commands = set(re.findall(r'add\("([a-z][a-z-]*)"', src.get("namecheck", "")))
    options = {m for s in src.values() for m in re.findall(r'["\'](--[a-z][a-z0-9-]*)["\']', s)} | {"--help"}  # argparse 기본
    names = {}
    for mod, s in src.items():
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        defs = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))}
        defs |= {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
        names[mod] = defs
    return commands, options, names


def dead(text: str, repo) -> list[tuple[str, str, int]]:
    """[(규칙, 대상, 줄)]"""
    commands, options, names = _index(str(repo))
    every = set().union(*names.values()) if names else set()
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        for kind, v in extract(line):
            if kind == "command" and v not in commands:
                out.append(("D001", v, i))
            elif kind == "option" and v not in options:
                out.append(("D002", v, i))
            elif kind == "path" and not PLACEHOLDER.search(v) and not (Path(repo) / v).exists():
                out.append(("D003", v, i))
            elif kind == "symbol":
                mod, _, attr = v.rpartition(".")
                if mod and mod in names and attr not in names[mod]:
                    out.append(("D004", v, i))
                elif not mod and v not in every and line.find(f"{v}()") >= 0:
                    out.append(("D004", v, i))
    return out
