"""격리 평가자: 답변 설명문이 의도와 같은 뜻인지 별도 모델이 사람 관점에서 본다(경고만, 제외는 규칙이 한다).

사용: python scripts/review_explanations.py <rules.json> <out.json> <표본.jsonl …> [--reviewer claude:sonnet] [--view end_user]
평가자는 후보를 만들거나 규칙을 쓴 쪽과 다른 격리 프로세스다. 받는 것: 의도(목적·사람 행동)·이웃 개념 이름·설명문.
받지 않는 것: 규칙 신호어(must·misread_as), 규칙 판정 결과, 다른 이름 후보.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_terms as ct  # noqa: E402
import collect_samples as cs  # noqa: E402

VIEWS = {
    "end_user": "이름을 처음 보는 일반 사용자의 입장에서 판단하세요.",
    "ux": "화면에서 이 이름을 보고 무엇을 할지 고르는 사람의 입장에서 판단하세요.",
}
INSTR = (
    "당신은 이름 검토자입니다. '의도'는 이 이름을 지은 사람이 전하려는 뜻이고, '설명'은 이름만 본 사람들이 받아들인 뜻입니다. "
    "{view} 설명마다 의도와 같은 뜻인지 고르세요: 같음 / 다른 뜻 / 불분명. 다른 뜻이면 무엇으로 읽혔는지 짧게 적으세요. "
    "'헷갈리면 안 되는 것'과 가까우면 다른 뜻입니다.\n"
    "설명 번호마다 한 줄씩, 예: 1. 다른 뜻 — 읽힌 뜻"
)
# 구조화된 출력용: 형식은 schema가 정하므로 줄 형식 예시를 뺀다. 평가자는 의도를 알고 보기에서 고르는 주체라
# 형식 신호의 영향이 작다(응답자·작명자와 다름, 사용자 2026-11-06 "그래서 주체를 구분하는게 중요")
INSTR_STRUCT = INSTR.rsplit("\n", 1)[0]
SCHEMA = {"type": "object", "required": ["items"], "properties": {"items": {"type": "array", "items": {
    "type": "object", "required": ["no", "verdict", "read_as"],
    "properties": {"no": {"type": "integer"}, "verdict": {"type": "string", "enum": ["같음", "다른 뜻", "불분명"]},
                   "read_as": {"type": "string"}}}}}}
MAX_ROUNDS = 3
VERDICTS = ("같음", "다른 뜻", "불분명")


def intent_of(rule: dict) -> str:
    acts = rule.get("human_actions") or []
    acts = " ".join(f'{a["object"]}을(를) {a["action"]}.' if isinstance(a, dict) else f"{a[0]}을(를) {a[1]}." for a in acts)
    return f'{rule.get("purpose", "")}. 사람이 하는 일: {acts}'.strip()


def explanations(rules: dict, files: list) -> dict:
    """rid → 같은 이름의 새 표본(stale·legacy·대조 제외) 설명문 목록."""
    out = {rid: [] for rid in rules}
    for f in files:
        for kind, e, items in ct._read(Path(f)):
            if items is None or kind == "legacy" or e.get("role") == "contrast":
                continue
            for it in items:
                rid = it.get("id")
                if rid in rules and it.get("term") == rules[rid]["term"] \
                        and e.get("rule_hashes", {}).get(rid) == ct.rule_hash(rules[rid]):
                    out[rid].append(it.get("explanation", ""))
    return out


LINE = re.compile(r"^\s*(\d+)\s*[.)]\s*(같음|다른 뜻|불분명)\s*(?:[—–\-:]\s*(.*))?$")


def prompt_for(rule: dict, texts: list[str], instr: str) -> str:
    near = ", ".join(rule.get("distinct_from", {})) or "없음"
    body = "\n".join(f"{i}. {t}" for i, t in enumerate(texts, 1))
    return f"{instr}\n\n의도: {intent_of(rule)}\n헷갈리면 안 되는 것: {near}\n\n설명:\n{body}"


def parse(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        m = LINE.match(line.strip().lstrip("-* "))
        if m:
            out[int(m.group(1)) - 1] = {"verdict": m.group(2), "read_as": (m.group(3) or "").strip()}
    return out


def _items(out, n: int) -> dict:
    """평가자 출력(구조화된 dict 또는 평문) → {0부터 번호: {verdict, read_as}}. 보기 밖·범위 밖은 버린다."""
    if isinstance(out, dict):
        got = {}
        for it in out.get("items") or []:
            if isinstance(it, dict) and isinstance(it.get("no"), int):
                got[it["no"] - 1] = {"verdict": it.get("verdict"), "read_as": str(it.get("read_as") or "").strip()}
    else:
        got = parse(str(out))
    return {i: v for i, v in got.items() if 0 <= i < n and v["verdict"] in VERDICTS}


def ask(call, rule: dict, texts: list[str], instr: str, timeout: float):
    """수정 프로토콜: 형식이 틀리거나 빠진 번호만 새 번호로 다시 묻는다. 받아들인 번호는 다시 묻지 않는다. 최대 MAX_ROUNDS회."""
    items, log, pending = {}, [], list(range(len(texts)))
    for rnd in range(MAX_ROUNDS):
        got = _items(call(prompt_for(rule, [texts[i] for i in pending], instr), timeout), len(pending))
        for j, v in got.items():
            items[pending[j]] = v
        pending = [i for i in pending if i not in items]
        log.append({"round": rnd, "accepted": len(got), "pending": pending})
        if not pending:
            break
    return items, log


def review(rules: dict, files: list, call, view: str = "end_user", timeout: float = 300, structured: bool = False) -> dict:
    """call(프롬프트, timeout) → 평문 답 또는 구조화된 dict."""
    instr = (INSTR_STRUCT if structured else INSTR).format(view=VIEWS[view])
    res = {}
    for rid, texts in explanations(rules, files).items():
        r = rules[rid]
        s = {"term": r["term"], "view": view, "n": len(texts), "same": 0, "other": [], "unclear": 0, "error": ""}
        res[rid] = s
        if not texts:
            continue
        try:
            items, log = ask(call, r, texts, instr, timeout)
        except Exception as exc:  # noqa: BLE001 — 평가자 실패는 경고 없음으로 두고 기록만
            s["error"] = f"{type(exc).__name__}: {exc}"
            continue
        s["rounds"] = len(log)
        if set(items) != set(range(len(texts))):
            s["error"] = f"응답 {len(items)}/{len(texts)}개({len(log)}회 물음)"
        for i, t in enumerate(texts):
            v = items.get(i, {})
            if v.get("verdict") == "같음":
                s["same"] += 1
            elif v.get("verdict") == "다른 뜻":
                s["other"].append({"read_as": v.get("read_as", ""), "text": t})
            else:
                s["unclear"] += 1
    return res


def make_reviewer(kind: str, model: str, art_dir: Path, structured: bool = True):
    """구조화된 출력(claude --json-schema, LM Studio response_format)이 기본. structured=False면 평문.
    gpt는 동봉 실행기가 schema를 못 받아 쓰지 않는다."""
    import plain_runner

    if kind not in plain_runner.TEXT:
        raise SystemExit(f"평가자 백엔드는 {', '.join(plain_runner.TEXT)}만: {kind}")
    if structured:
        return lambda prompt, timeout: plain_runner.TEXT[kind](prompt, model, timeout, art_dir, schema=SCHEMA)
    return lambda prompt, timeout: plain_runner.TEXT[kind](prompt, model, timeout, art_dir)


def report_lines(rev: dict) -> list[str]:
    lines = ["", "## 격리 평가자(경고, 제외하지 않음)", "", "| 이름 | 관점 | 같음 | 다른 뜻 | 불분명 | 다르게 읽힌 뜻 |", "|---|---|---|---|---|---|"]
    for s in rev.values():
        reads = "; ".join(sorted({o["read_as"] for o in s["other"] if o["read_as"]}))[:120].replace("|", "/")
        lines.append(f'| {s["term"]} | {s["view"]} | {s["same"]}/{s["n"]} | {len(s["other"])} | {s["unclear"]} | '
                     f'{reads}{" (오류: " + s["error"] + ")" if s["error"] else ""} |')
    return lines


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    rules, out = ct.load_rules(Path(a[0])), Path(a[1])
    opts = {k: a[a.index(k) + 1] for k in ("--reviewer", "--view") if k in a}
    files = [x for x in a[2:] if not x.startswith("--") and x not in opts.values()]
    kind, model = opts.get("--reviewer", "claude:sonnet").split(":", 1)
    rev = review(rules, files, make_reviewer(kind, model, out.parent / "art_review"), opts.get("--view", "end_user"), structured=True)
    out.write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(report_lines(rev)))


if __name__ == "__main__":
    main()
