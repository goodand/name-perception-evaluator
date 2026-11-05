"""지시문 검사: 생성자·답변자·평가자에게 가는 지시문에서 개발·SW 단어를 찾아 경고한다(막지 않음).

사용: python scripts/prompt_check.py <파일 또는 문자열> [--json]
사전: docs/harness/dev_words.json(general = 범용, leaky = 실제로 섞여 들어갔던 단어). 영어는 단어 경계, 한국어는 부분 일치.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
WORDS = ROOT / "docs/harness/dev_words.json"


def load(path: Path = WORDS) -> dict:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v["words"] for k, v in d.items() if isinstance(v, dict) and "words" in v}


def check(text: str, words: dict | None = None) -> list[dict]:
    """[{word, dict, at}] 한 단어는 한 번만, 처음 나온 자리 기준."""
    words = words or load()
    low, hits, seen = text.lower(), [], set()
    for name, ws in words.items():
        for w in ws:
            w = w.lower()
            pat = re.escape(w) if re.search(r"[가-힣]", w) else rf"(?<![a-z]){re.escape(w)}(?![a-z])"
            m = re.search(pat, low)
            if m and w not in seen:
                seen.add(w)
                hits.append({"word": w, "dict": name, "at": text[max(0, m.start() - 15):m.end() + 15]})
    return sorted(hits, key=lambda h: text.lower().find(h["word"]))


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
    max_rounds 안에 안 되면 PromptRejected. allow[이름]은 이유가 기록된 예외 단어(예: gpt 실행기 형식 요구)."""
    allow, out, log = allow or {}, {}, []
    for name, text in prompts.items():
        holes = re.findall(r"\{[a-z_]+\}", text)
        for rnd in range(max_rounds + 1):
            hits = [h for h in check(text, words) if h["word"] not in allow.get(name, ())]
            broken = [h for h in holes if h not in text]
            log.append({"prompt": name, "round": rnd, "hits": [h["word"] for h in hits], "missing_slots": broken,
                        "allowed": sorted(allow.get(name, ())), "text": text})
            if not hits and not broken:
                out[name] = text
                break
            if reviser is None or rnd == max_rounds:
                raise PromptRejected(f'{name}: {", ".join(h["word"] for h in hits) or "자리표시 " + ", ".join(broken)}'
                                     f" — {rnd}번 고쳐도 남음, 응답자에게 보내지 않음")
            text = reviser(text, [h["word"] for h in hits])
    return out, log


def claude_reviser(model: str = "sonnet", timeout: float = 120):
    """격리 claude로 지시문을 고친다(plain_runner). 고친 결과는 gate가 다시 검사한다."""
    import plain_runner

    return lambda text, ws: plain_runner.claude_text(REVISE_INSTR.format(words=", ".join(ws), text=text), model, timeout)
