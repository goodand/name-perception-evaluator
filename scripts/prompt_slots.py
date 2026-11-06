"""지시문 틀 + 빈칸 채움 → 빈칸 검사 → 조사 맞춤 → 평문 지시문 (사용자 2026-11-06).

틀은 고정(docs/harness/prompt_templates.json). 바깥 에이전트는 빈칸 값만 채운다(JSON). 응답자에게는 완성된 평문만 간다.
수정 프로토콜: 걸린 빈칸만 다시 채운다. 다른 빈칸·틀을 바꾸면 거부, 이전에 걸린 값을 다시 내면 거부, 최대 3회, 대체어는 주지 않는다.
사용: python scripts/prompt_slots.py <틀 이름> <빈칸.json> [--json]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import prompt_check  # noqa: E402

ROOT = Path(__file__).parents[1]
TEMPLATES = ROOT / "docs/harness/prompt_templates.json"
HOLE = re.compile(r"\{([^{}|]+)(?:\|([^{}]+))?\}")
_KIWI = None


class SlotRejected(Exception):
    """수정 횟수 안에 빈칸이 깨끗해지지 않았다. 응답자에게 보내지 않는다."""


def load(path: Path = TEMPLATES) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def template_hash(template: str) -> str:
    return hashlib.sha256(template.encode("utf-8")).hexdigest()[:12]


def holes(template: str) -> list[str]:
    return list(dict.fromkeys(m.group(1) for m in HOLE.finditer(template)))


TAIL = re.compile(r"(\S)[\s.,!?;:'\"’”)\]」』]*$")  # 끝의 공백·문장부호만 건너뛰고 마지막 글자를 본다


class NoJosa(ValueError):
    """조사를 정할 수 없는 값(영어·숫자 끝). 조사 없는 자리에 두거나 한글로 다시 채운다.
    숫자는 용어에 거의 쓰이지 않아 읽기 규칙을 두지 않는다(사용자 2026-11-06)."""


def _kiwi():
    global _KIWI
    if _KIWI is None:
        from kiwipiepy import Kiwi
        _KIWI = Kiwi()
    return _KIWI


def _josa(word: str, josa: str) -> str:
    """끝 글자로 갈래를 나눈다: 한글 → Kiwi, 영어·숫자 → NoJosa(Kiwi는 한국어용)."""
    m = TAIL.search(word)
    if not m or not re.fullmatch(r"[가-힣]", m.group(1)):
        raise NoJosa(f"조사를 붙일 수 없는 값: {word}")
    tag = {"이": "JKS", "을": "JKO", "은": "JX", "의": "JKG", "와": "JKB", "로": "JKB", "으로": "JKB"}.get(josa, "JX")
    last = _kiwi().tokenize(word)[-1]  # 마지막 형태소에 조사를 붙여 받침을 맞춘다
    return word[:last.start] + _kiwi().join([(last.form, last.tag), (josa, tag)])


def josa_holes(template: str) -> set[str]:
    return {m.group(1) for m in HOLE.finditer(template) if m.group(2)}


def render(template: str, slots: dict, kiwi: bool = True) -> str:
    def sub(m):
        v = slots[m.group(1)]
        if not m.group(2):
            return v
        return _josa(v, m.group(2)) if kiwi else v + m.group(2)
    return HOLE.sub(sub, template)


def check_slots(slots: dict, words: dict | None = None, allow=()) -> list[dict]:
    return [{"slot": k, "value": v, "words": [h["word"] for h in hs], "dict": sorted({h["dict"] for h in hs})}
            for k, v in slots.items()
            if (hs := [h for h in prompt_check.check(v, words) if h["word"] not in allow])]


def gate(template: str, slots: dict, filler=None, max_rounds: int = 3, words: dict | None = None, allow=(),
         kiwi: bool = True):
    """→ (평문 지시문, 기록). filler(요청)은 {"hits": [...], "round", "max_rounds"}를 받아 걸린 빈칸의 새 값 dict를 돌려준다."""
    need = holes(template)
    missing = [h for h in need if h not in slots]
    if missing:
        raise SlotRejected(f"빈칸 없음: {', '.join(missing)}")
    slots, log, seen = dict(slots), [], {}
    for rnd in range(max_rounds + 1):
        hits = check_slots(slots, words, allow)
        for k in sorted((josa_holes(template) if kiwi else set()) - {h["slot"] for h in hits}):
            try:
                _josa(slots[k], "이")
            except NoJosa:
                hits.append({"slot": k, "value": slots[k], "words": [], "dict": ["조사 자리에 영어"]})
        log.append({"round": rnd, "template_hash": template_hash(template), "slots": dict(slots), "hits": hits})
        if not hits:
            return render(template, slots, kiwi), log
        for h in hits:
            seen.setdefault(h["slot"], set()).add(h["value"])
        if filler is None or rnd == max_rounds:
            raise SlotRejected(f'{", ".join(h["slot"] for h in hits)} — {rnd}번 고쳐도 걸림, 응답자에게 보내지 않음')
        new = filler({"status": "rejected", "round": rnd + 1, "max_rounds": max_rounds,
                      "hits": [{k: h[k] for k in ("slot", "value", "words", "dict")} for h in hits]})
        hit_slots = {h["slot"] for h in hits}
        extra = set(new) - hit_slots
        if extra:
            raise SlotRejected(f"걸리지 않은 빈칸을 바꾸려 함: {', '.join(sorted(extra))}")
        again = [k for k, v in new.items() if v in seen.get(k, ())]
        if again:
            raise SlotRejected(f"이전에 걸린 값을 다시 냄: {', '.join(again)}")
        slots.update(new)


FILL_INSTR = ("아래 빈칸 값에 쓰면 안 되는 낱말이 들어 있습니다. 뜻은 그대로 두고 그 낱말 없이 다시 적어 주세요. "
              "빈칸마다 한 줄씩, '빈칸 이름: 새 값' 꼴로만 적어 주세요.\n\n{lines}")


def claude_filler(model: str = "haiku", timeout: float = 120):
    """격리 claude가 걸린 빈칸만 다시 채운다(실험용 바깥 에이전트 대역). 평문으로 받고 평문으로 읽는다."""
    import plain_runner

    def fill(req):
        lines = "\n".join(f'{h["slot"]}: {h["value"]} (쓰면 안 되는 낱말: {", ".join(h["words"])})' for h in req["hits"])
        with plain_runner.usage(actor="빈칸 채우기"):
            out = plain_runner.claude_text(FILL_INSTR.format(lines=lines), model, timeout)
        want = {h["slot"] for h in req["hits"]}
        got = {}
        for ln in out.splitlines():
            k, _, v = ln.strip().partition(":")
            if k.strip() in want and v.strip():
                got[k.strip()] = v.strip()
        return got
    return fill


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    name, src = sys.argv[1], Path(sys.argv[2])
    t = load()
    slots = {**t["defaults"].get(name, {}), **json.loads(src.read_text(encoding="utf-8"))}
    try:
        text, log = gate(t["templates"][name], slots)
    except SlotRejected as e:
        print(json.dumps({"status": "rejected", "reason": str(e), "hits": check_slots(slots)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"status": "ok", "text": text, "log": log}, ensure_ascii=False) if "--json" in sys.argv else text)


if __name__ == "__main__":
    main()
