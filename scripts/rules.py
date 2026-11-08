"""규칙 엔진: 규칙마다 고정 ID·심각도·순수 함수, 결과는 같은 꼴의 진단(SkillMD rules.ts 방식, 사용자 2026-11-06).

외부 에이전트는 ID로 분기하고(JSON), 사람용 보고서는 같은 진단에서 표로 만든다. 검사 내용은 기존 함수를 그대로 감싼다.
규칙은 필요한 입력이 ctx에 없으면 돌지 않는다. ID는 바꾸지 않는다(시험이 고정).
  N001 이름 형식(error)      ctx: names, sep
  N002 키워드 수(error)       ctx: names, sep, max_keywords
  P001 지시문 개발 용어 막음(error)  ctx: prompts {이름: 글}, words(선택)
  P002 지시문 개발 용어 경고(warn)   ctx: prompts, words(선택)
  B001 브리프 형식(error)     ctx: brief
  D001~D004 죽은 참조(error)  ctx: docs {파일: 글}, repo — 명령·옵션·경로·함수(doc_refs.py)
"""
from dataclasses import asdict, dataclass
from typing import Callable

SEVERITIES = ("error", "warn", "info")


@dataclass(frozen=True)
class Diagnostic:
    id: str
    severity: str
    message: str
    where: str = ""  # 이름·지시문 이름 등 걸린 대상
    file: str = ""
    line: int | None = None


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    description: str
    needs: tuple[str, ...]
    check: Callable[[dict], list]  # ctx → [(message, where)]


REGISTRY: dict[str, Rule] = {}


def rule(id_: str, severity: str, description: str, needs: tuple[str, ...]):
    assert severity in SEVERITIES and id_ not in REGISTRY

    def deco(fn):
        REGISTRY[id_] = Rule(id_, severity, description, needs, fn)
        return fn
    return deco


@rule("N001", "error", "이름 형식(영어 소문자 하이픈·밑줄, 또는 한글 낱말 띄어쓰기)", ("names",))
def _n001(ctx):
    import namecheck
    sep = ctx.get("sep", "-")
    return [(f"형식이 '{sep}' 규칙에 맞지 않음", n) for n in ctx["names"] if not namecheck.NAME_RE[sep].match(n)]


@rule("N002", "error", "키워드 수 상한", ("names", "max_keywords"))
def _n002(ctx):
    sep = ctx.get("sep", "-")
    return [(f"키워드 {len(n.split(sep))}개(최대 {ctx['max_keywords']})", n) for n in ctx["names"]
            if len(n.split(sep)) > ctx["max_keywords"]]


def _prompt_hits(ctx, level):
    import prompt_check
    return [(f'"{h["word"]}"({h["dict"]}) …{h["at"]}…', name) for name, text in ctx["prompts"].items()
            for h in prompt_check.check(text, ctx.get("words"), level)]


@rule("P001", "error", "지시문에 개발 용어(표제어 일치): 보내지 않음", ("prompts",))
def _p001(ctx):
    return _prompt_hits(ctx, "block")


@rule("P002", "warn", "지시문에 개발 용어가 낱말 안에 포함: LLM이 판단", ("prompts",))
def _p002(ctx):
    return _prompt_hits(ctx, "warn")


@rule("B001", "error", "브리프 형식(삼중항·필수 칸·빈칸)", ("brief",))
def _b001(ctx):
    import namecheck
    return [(m, "brief") for m in namecheck.check_brief(ctx["brief"])]


def _refs(kind):
    def check(ctx):
        import doc_refs
        return [(msg, v, f, ln) for f, text in ctx["docs"].items() for rid, v, ln in doc_refs.dead(text, ctx["repo"])
                if rid == kind for msg in [f"문서가 가리키는 대상이 지금 코드에 없음: {v}"]]
    return check


for _id, _what in (("D001", "namecheck 명령"), ("D002", "--옵션"), ("D003", "저장소 안 경로"), ("D004", "함수·속성")):
    rule(_id, "error", f"죽은 참조: 문서의 {_what}가 코드에 없음", ("docs", "repo"))(_refs(_id))


def run(ctx: dict, only=None) -> list[Diagnostic]:
    """ctx에 입력이 있는 규칙만, ID 순서로 돌린다."""
    out = []
    for rid in sorted(only or REGISTRY):
        r = REGISTRY[rid]
        if all(k in ctx for k in r.needs):
            for hit in r.check(ctx):  # (메시지, 대상) 또는 (메시지, 대상, 파일, 줄)
                m, w, f, ln = (*hit, ctx.get("file", ""), None)[:4] if len(hit) == 2 else hit
                out.append(Diagnostic(r.id, r.severity, m, w, f, ln))
    return out


def report(diags: list[Diagnostic]) -> dict:
    counts = {s: sum(d.severity == s for d in diags) for s in SEVERITIES}
    return {"counts": counts, "exit": 1 if counts["error"] else 0, "diagnostics": [asdict(d) for d in diags]}
