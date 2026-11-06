"""지시문 검사: 생성자·답변자·평가자에게 가는 지시문에서 개발·SW 단어를 찾는다. 표제어 일치는 막고, 낱말 안 포함은 경고.

사용: python scripts/prompt_check.py <파일 또는 문자열> [--json]
사전: docs/harness/dev_words.json(general = 범용, leaky = 실제로 섞여 들어갔던 단어). 영어는 표제어(simplemma), 한국어는 부분 일치.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORDS = ROOT / "docs/harness/dev_words.json"


def load(path: Path = WORDS) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    words = {k: v["words"] for k, v in d.items() if isinstance(v, dict) and "words" in v}
    bad = [w for ws in words.values() for w in ws if not re.fullmatch(r"[a-z]+( [a-z]+)*|[가-힣 ]+", w.strip().lower())]
    if bad:  # 기호가 섞이면 낱말 쪼개기가 달라져 엉뚱한 글을 막는다(c++ → c). 정리 세션 반례
        raise ValueError(f"사전 낱말에 영어 소문자·한글·띄어쓰기 말고 다른 글자가 있음: {bad}")
    return words


_LEMMA = {}


def lemma(w: str) -> str:
    """영어 낱말 표제어(simplemma 2.0.0, 사전 표 + 규칙이라 재현됨: 2026-11-06 비교에서 놓침 0·잘못 잡음 0)."""
    if w not in _LEMMA:
        import simplemma
        _LEMMA[w] = simplemma.lemmatize(w, lang="en").lower()
    return _LEMMA[w]


def tokens(text: str) -> list[str]:
    """영어 낱말로 쪼갠다. 하이픈·여러 공백·문장부호는 모두 경계."""
    return re.findall(r"[a-z]+", text.lower())


def _at(text: str, i: int, j: int) -> str:
    return text[max(0, i - 15):j + 15]


def check(text: str, words: dict | None = None, level: str = "block") -> list[dict]:
    """[{word, dict, at, level}] 한 단어는 한 번만, 처음 나온 자리 기준.
    두 단계(사용자 2026-11-06, 비교 실험으로 선택):
      block = 막음. 영어는 낱말마다 표제어로 바꿔 사전 낱말(여러 낱말이면 이어진 순서)의 표제어와 같을 때, 한국어는 부분 일치
      warn  = 경고만(LLM이 보고 판단). 영어 낱말 안에 사전 낱말이 들어 있을 때(pytest ⊃ test, contest ⊃ test). 3글자 이상만
    level="block"이면 막을 것만, "warn"이면 경고만, "all"이면 둘 다."""
    words = words or load()
    low, hits, seen = text.lower(), [], set()
    toks = tokens(text)
    lem = [lemma(t) for t in toks]
    for name, ws in words.items():
        for w in ws:
            w = w.lower().strip()
            if not w or w in seen:
                continue
            if re.search(r"[가-힣]", w):
                i = low.find(w)
                if i >= 0 and level in ("block", "all"):
                    seen.add(w)
                    hits.append({"word": w, "dict": name, "at": _at(text, i, i + len(w)), "level": "block"})
                continue
            wl = [lemma(t) for t in tokens(w)]
            if not wl:
                continue
            blocked = any(lem[i:i + len(wl)] == wl for i in range(len(lem) - len(wl) + 1))
            if blocked:
                found = "block"
            elif len(wl) == 1 and len(w) >= 3 and any(w in t for t in toks):
                found = "warn"
            else:
                continue
            if level in (found, "all"):
                seen.add(w)
                head = tokens(w)[0]
                i = max(low.find(head), 0)
                hits.append({"word": w, "dict": name, "at": _at(text, i, i + len(head)), "level": found})
    return sorted(hits, key=lambda h: low.find(h["word"].split()[0]))


def warnings(text: str, words: dict | None = None) -> list[dict]:
    return check(text, words, "warn")


def check_prompts(prompts: dict, words: dict | None = None) -> list[str]:
    """{이름: 지시문} → 경고 문장 목록."""
    return [f'지시문 {name}: "{h["word"]}"({h["dict"]}) …{h["at"]}…' for name, text in prompts.items()
            for h in check(text, words)]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    src = sys.argv[1]
    text = Path(src).read_text(encoding="utf-8") if Path(src).is_file() else src
    hits = check(text)
    print(json.dumps(hits, ensure_ascii=False, indent=1) if "--json" in sys.argv
          else "\n".join(f'{h["word"]} ({h["dict"]}): …{h["at"]}…' for h in hits) or "경고 없음")


if __name__ == "__main__":
    main()


# ---- 거름 루프: 걸린 지시문은 보내지 않고, 고침 → 다시 검사를 반복한다(사용자 2026-11-05) ----
class PromptRejected(Exception):
    """고침 횟수 안에 깨끗해지지 않은 지시문. 응답자에게 보내지 않는다."""


REVISE_INSTR = (
    "아래 글은 다른 사람에게 줄 요청문입니다. 뜻과 요구는 그대로 두고, 다음 단어를 쓰지 않도록 다시 써 주세요: {words}. "
    "중괄호로 된 자리표시(예: {{view}})는 그대로 두세요. 다시 쓴 요청문만 적어 주세요.\n\n{text}"
)


def gate(prompts: dict, reviser=None, max_rounds: int = 3, allow: dict | None = None, words: dict | None = None):
    """{이름: 지시문} → ({이름: 깨끗한 지시문}, 기록). 걸린 단어가 있으면 reviser(지시문, 단어들)로 고치고 다시 검사.
    max_rounds 안에 안 되면 PromptRejected. 실제 실행에서는 reviser를 두지 않는다(고쳐 쓰는 모델은 재현되지 않음):
    고칠 곳은 틀의 빈칸(prompt_slots)으로 옮기고 외부 에이전트가 채운다. allow[이름]은 이유가 기록된 예외 단어(예: gpt 실행기 형식 요구)."""
    allow, out, log = allow or {}, {}, []
    for name, text in prompts.items():
        holes = re.findall(r"\{[a-z_]+\}", text)
        for rnd in range(max_rounds + 1):
            hits = [h for h in check(text, words) if h["word"] not in allow.get(name, ())]
            broken = [h for h in holes if h not in text]
            log.append({"prompt": name, "round": rnd, "hits": [h["word"] for h in hits], "missing_slots": broken,
                        "warnings": [h["word"] for h in warnings(text, words)],
                        "allowed": sorted(allow.get(name, ())), "text": text})
            if not hits and not broken:
                out[name] = text
                break
            if reviser is None or rnd == max_rounds:
                raise PromptRejected(f'{name}: {", ".join(h["word"] for h in hits) or "자리표시 " + ", ".join(broken)}'
                                     f" — {rnd}번 고쳐도 남음, 응답자에게 보내지 않음")
            text = reviser(text, [h["word"] for h in hits])
    return out, log
