"""검색자(내부 주체)와 키워드 점검(외부 에이전트, 수정 프로토콜) (사용자 2026-11-06).

1) 검색자: 설명문(하는 일·사람 행동)만 받는 격리 모델이 웹에서 사람들이 실제로 쓰는 낱말을 찾는다.
   세션 맥락·분야 이름은 주지 않는다. 지시문은 보내기 전에 개발 용어 사전으로 검사(걸리면 보내지 않음).
2) 사전 검사: 낱말마다 개발 용어 경고를 붙인다(막지 않음).
3) 점검: 외부 에이전트가 JSON으로 낱말마다 남김·뺌을 정한다. 규칙으로 검사하고, 걸린 항목만 다시 내게 한다.
   - 검색자가 낸 낱말만(새 낱말 거부), 낱말마다 한 번, 뺄 때는 정해진 이유(기타는 설명 필수)
   - 이미 받아들인 항목은 바꿀 수 없음, 거부 최대 3회 → 넘으면 멈추고 사람이 정한다
   - 뺀 낱말은 사용자에게 따로 보인다(외부 에이전트의 편향은 주로 빼는 쪽에서 드러난다)
남긴 낱말은 combine의 키워드 풀에 더한다(작명자에게는 주지 않음).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prompt_check  # noqa: E402

REASONS = ("뜻이 다름", "너무 넓음", "개발 용어 경고", "기타")
MAX_ROUNDS = 3
SEARCH_INSTR = (
    "아래 일을 사람들이 실제로 어떤 낱말로 부르는지 찾아 주세요. 사전과 여러 사람이 쓴 글을 찾아보고, "
    "많이 쓰이는 영어 낱말을 골라 주세요.\n\n하는 일: {purpose}\n사람이 하는 일: {human_actions}\n\n"
    "낱말마다 한 줄씩, '영어 낱말 — 한국어 뜻 — 찾은 곳 주소' 꼴로 {n}개 적어 주세요. 다른 말은 쓰지 마세요."
)
LINE = re.compile(r"^\s*(?:\d+[.)]\s*)?([A-Za-z][A-Za-z ]*?)\s*[—-]{1,2}\s*(.+?)\s*[—-]{1,2}\s*(\S+)\s*$")


def search_prompt(brief: dict, n: int = 15) -> str:
    acts = brief.get("human_actions", [])
    if isinstance(acts, list):
        acts = "; ".join(" ".join(str(v) for v in a.values()) if isinstance(a, dict) else str(a) for a in acts)
    return SEARCH_INSTR.format(purpose=brief["purpose"], human_actions=acts, n=n)


def parse(text: str) -> list[dict]:
    out, seen = [], set()
    for ln in text.splitlines():
        m = LINE.match(ln)
        if m:
            w = m.group(1).strip().lower()
            if w not in seen:
                seen.add(w)
                out.append({"word": w, "meaning": m.group(2), "source": m.group(3)})
    return out


def keywords(phrases) -> list[str]:
    """남긴 구절(brand name testing)을 낱말로 쪼개 겹친 것은 하나로(combine 키워드 풀용). 순서는 처음 나온 대로."""
    return list(dict.fromkeys(t for p in phrases for t in re.findall(r"[a-z]+", p.lower())))


def search(brief: dict, call, n: int = 15, words: dict | None = None) -> dict:
    """call(지시문) → 평문. 지시문이 사전에 걸리면 보내지 않는다(prompt_check.PromptRejected)."""
    prompt = search_prompt(brief, n)
    hits = prompt_check.check(prompt, words)
    if hits:
        raise prompt_check.PromptRejected(f'검색자 지시문: {", ".join(h["word"] for h in hits)} — 설명문을 고칠 것')
    found = parse(call(prompt))
    for f in found:
        f["warnings"] = [h["word"] + ("" if h["level"] == "block" else "(포함)")
                         for h in prompt_check.check(f["word"] + " " + f["meaning"], words, "all")]
    return {"words": found, "round": 0, "max_rounds": MAX_ROUNDS, "accepted": {}, "history": []}


def claude_searcher(model: str = "sonnet", timeout: float = 300):
    import plain_runner

    def call(prompt):
        with plain_runner.usage(actor="검색자"):
            return plain_runner.claude_text(prompt, model, timeout, tools="WebSearch,WebFetch")
    return call


def _locked(d: dict) -> tuple:
    """받아들인 항목에서 바꿀 수 없는 부분: 남김이면 keep만, 뺌이면 keep·이유·note."""
    return (d["keep"],) if d["keep"] else (d["keep"], d.get("reason"), d.get("note", ""))


def review(state: dict, decisions: list[dict]) -> dict:
    """외부 에이전트의 점검 제출 하나를 검사한다. state는 제자리에서 갱신. 돌려주는 값은 에이전트에게 줄 JSON."""
    if state.get("stopped"):  # 멈춘 뒤에는 어떤 제출도 받지 않는다(사람이 정한다)
        return {"status": "stopped", "reason": "이미 멈춤 — 사람이 정할 것", "errors": [], "missing": []}
    names = {w["word"].lower() for w in state["words"]}
    acc, errors, ok, seen = state["accepted"], [], {}, set()
    for d in decisions:
        w = str(d.get("word", "")).lower()
        e = None
        if w not in names:
            e = "검색자가 내지 않은 낱말"
        elif w in seen:
            e = "같은 낱말을 두 번 냄"
        elif not isinstance(d.get("keep"), bool):
            e = "keep은 true 또는 false"
        elif not d["keep"] and d.get("reason") not in REASONS:
            e = f"뺄 때 이유는 {', '.join(REASONS)} 중 하나"
        elif "note" in d and not isinstance(d["note"], str):
            e = "note는 글이어야 함"
        elif not d["keep"] and d["reason"] == "기타" and not d.get("note", "").strip():
            e = "기타는 note 필수"
        elif w in acc and _locked(acc[w]) != _locked(d):
            e = "이미 받아들인 항목은 바꿀 수 없음"
        seen.add(w)
        if e:
            errors.append({"word": w, "error": e})
        elif w not in acc:
            ok[w] = {"keep": d["keep"], **({"reason": d["reason"], "note": d.get("note", "")} if not d["keep"] else {})}
    acc.update(ok)
    missing = sorted(names - set(acc) - {x["word"] for x in errors})  # 낸 적도 없는 낱말
    state["history"].append({"round": state["round"], "accepted_now": sorted(ok), "errors": errors, "missing": missing})
    if not errors and not missing:
        keep = sorted(w for w in names if acc[w]["keep"])
        return {"status": "ok", "keep": keep, "dropped": [{"word": w, **acc[w]} for w in sorted(names - set(keep))]}
    state["round"] += 1
    if state["round"] > state["max_rounds"]:
        state["stopped"] = True
        return {"status": "stopped", "reason": f'{state["max_rounds"]}번 넘게 거부 — 사람이 정할 것', "errors": errors,
                "missing": missing}
    return {"status": "rejected", "round": state["round"], "max_rounds": state["max_rounds"], "errors": errors,
            "missing": missing, "fix_only": sorted({x["word"] for x in errors} | set(missing))}
