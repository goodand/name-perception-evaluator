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
