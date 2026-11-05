"""이름 후보 생성(격리)과 키워드 통계 (하네스 v2.2).

사용:
  python scripts/name_keywords.py generate <model,model,…> <out_dir> [--brief b.json]  # 묶음마다 새 격리 프로세스, 20개씩
  python scripts/name_keywords.py stats <batch.json…>                      # 키워드 등장 횟수·묶음 등장 수·함께 쓰인 단어
  python scripts/name_keywords.py risk --rules <rules> --samples <…> [--allow-stale]   # 검증 결과를 키워드 단위로
생성 프롬프트에는 하는 일·사람 행동만 넣는다(분야 이름·금지 목록·실패 단어 없음 — 사용자 2026-11-04).
생성자와 답변자는 서로 다른 격리 프로세스다. 생성 결과의 설명(why)은 답변자에게 주지 않는다.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

ROOT = Path(__file__).parents[1]


def _object_particle(word: str) -> str:
    """목적격 조사: 마지막 글자에 받침이 있으면 '을', 없으면 '를'(한글이 아니면 '를')."""
    ch = word.strip()[-1:] or "가"
    return "을" if "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 else "를"


def gen_prompt(brief: dict, profile: dict, n: int = 20) -> str:
    """프로필의 격리 생성 틀 + 브리프의 목적·사람 행동. 분야 이름·금지 목록·실패 단어는 넣지 않는다."""
    pairs = [(a["object"], a["action"]) if isinstance(a, dict) else (a[0], a[1]) for a in brief["human_actions"]]
    acts = " ".join(f"{o}{_object_particle(o)} {v}." for o, v in pairs)  # 주체는 늘 사람이라 프롬프트에는 대상·행동만
    return profile["generator"]["prompt_template"].format(purpose=brief["purpose"].rstrip(". "), human_actions=acts,
                                                          max_keywords=profile["max_keywords"], n=n)


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# 기본 = 예시 브리프(이름 짓는 하네스 자체). 2026-11-04 생성 묶음과 같은 문자열이다.
GEN_PROMPT = gen_prompt(_load(ROOT / "docs/harness/briefs/name-harness.json"), _load(ROOT / "docs/harness/naming_profile.json"))


def normalize(name: str) -> str:
    s = re.sub(r"\s+", "-", str(name).strip().lower())
    s = re.sub(r"[^a-z0-9_-]", "", s)
    return re.sub(r"-{2,}", "-", s).strip("-_")


def tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[-_]", name) if t]


PLAIN_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])?\s*([a-z][a-z0-9 _]*(?:-[a-z0-9 _]+)*?)\s*(?:(?:\s[—–-]\s|[—–:]\s*)(.*))?$", re.I)


def parse_plain(text: str) -> dict:
    """평문 '이름 — 떠오르는 일' 줄들 → {"candidates": [...]} (parse_candidates가 받는 모양)."""
    cands = []
    for line in str(text).splitlines():
        m = PLAIN_LINE.match(line.strip().strip("`"))
        if m and m.group(1).strip():
            cands.append({"name": m.group(1).strip(), "why": (m.group(2) or "").strip()})
    return {"candidates": cands}


def parse_candidates(out) -> list[dict]:
    """생성 출력(평문 또는 {"candidates": [...]}) → [{name, why}] (정규화, 이름 없음·중복 제외)."""
    if isinstance(out, str):
        out = parse_plain(out)
    if not isinstance(out, dict) or not isinstance(out.get("candidates"), list):
        return []
    seen, got = set(), []
    for c in out["candidates"]:
        n = normalize(c.get("name", "")) if isinstance(c, dict) else ""
        if n and n not in seen:
            seen.add(n)
            got.append({"name": n, "why": c.get("why", "")})
    return got


def keyword_stats(batches: list[list[str]]) -> dict:
    """키워드 → {count: 서로 다른 이름 수, batches: 등장 묶음 수, names}."""
    st = {}
    for b in batches:
        in_batch = set()
        for name in dict.fromkeys(b):  # 묶음 안 같은 이름 중복 제거
            for t in dict.fromkeys(tokens(name)):
                s = st.setdefault(t, {"count": 0, "batches": 0, "names": []})
                if name not in s["names"]:
                    s["names"].append(name)
                    s["count"] += 1
                in_batch.add(t)
        for t in in_batch:
            st[t]["batches"] += 1
    return st


def ranked(st: dict) -> list:
    return sorted(st.items(), key=lambda kv: (-kv[1]["batches"], -kv[1]["count"], kv[0]))


def pairs(batches: list[list[str]]) -> Counter:
    """함께 쓰인 키워드 쌍(순서 무시) — 서로 다른 이름 단위로 센다."""
    names = dict.fromkeys(n for b in batches for n in b)
    c = Counter()
    for n in names:
        ts = sorted(set(tokens(n)))
        for i in range(len(ts)):
            for j in range(i + 1, len(ts)):
                c[(ts[i], ts[j])] += 1
    return c


def diversity(by_source: dict) -> dict:
    """생성자(모델)별 다양성. names=서로 다른 이름 수, distinct_tokens=서로 다른 키워드 수,
    unique_tokens=다른 생성자 묶음에 한 번도 안 나온 키워드 수, within_overlap=같은 생성자 묶음끼리 키워드 Jaccard 평균(높을수록 반복)."""
    toks = {s: {t for b in bs for n in b for t in tokens(n)} for s, bs in by_source.items()}
    out = {}
    for s, bs in by_source.items():
        others = set().union(*(v for k, v in toks.items() if k != s)) if len(toks) > 1 else set()
        sets = [{t for n in b for t in tokens(n)} for b in bs]
        jac = [len(a & b) / len(a | b) for i, a in enumerate(sets) for b in sets[i + 1:] if a | b]
        out[s] = {"batches": len(bs), "names": len({n for b in bs for n in b}), "distinct_tokens": len(toks[s]),
                  "unique_tokens": len(toks[s] - others), "within_overlap": sum(jac) / len(jac) if jac else 0.0}
    return out


def combine(batches: list[list[str]], max_keywords: int = 3, top: int = 30, min_batches: int = 2) -> list[dict]:
    """생성 묶음에서 키워드를 뽑아 새 후보를 규칙으로 조합한다(사람·평가자 판단 없음, 사용자 2026-11-04 지시).
    - 키워드는 min_batches개 이상 묶음에 나온 것만(우연한 단어 제외)
    - 자리: 생성 이름에서 그 키워드가 맨 앞에 온 횟수가 많으면 앞(대상), 맨 뒤가 많으면 뒤(역할). [대상]-[역할] 순서를 따른다
    - 한 이름 안에서 키워드 중복 없음, 이미 생성된 이름은 뺌, 키워드 수는 2~max_keywords
    - 점수 = 키워드 등장 묶음 수의 합. 동점은 이름순"""
    st = keyword_stats(batches)
    seen = {n for b in batches for n in b}
    first, last = Counter(), Counter()
    for n in seen:
        ts = tokens(n)
        if len(ts) > 1:
            first[ts[0]] += 1
            last[ts[-1]] += 1
    keep = [k for k, v in st.items() if v["batches"] >= min_batches]
    heads = [k for k in keep if first[k] > last[k]]
    tails = [k for k in keep if last[k] > first[k]]
    mids = [k for k in keep if k not in heads and k not in tails]
    out = {}
    for h in heads:
        for t in tails:
            if h == t:
                continue
            cands = [[h, t]] + ([[h, m, t] for m in heads + mids if m not in (h, t)] if max_keywords >= 3 else [])
            for ks in cands:
                name = "-".join(ks)
                if name not in seen and len(set(ks)) == len(ks):
                    out[name] = {"name": name, "keywords": ks, "score": sum(st[k]["batches"] for k in ks),
                                 "source": "combine"}
    return sorted(out.values(), key=lambda c: (len(c["keywords"]), -c["score"], c["name"]))[:top]  # 짧은 이름 먼저


def token_outcomes(res: dict) -> dict:
    """check_terms.score() 결과 → 키워드별 {names, pass, n, misread_n, excluded}. 표본 0개 이름은 뺀다."""
    out = {}
    for s in res.values():
        if not s["n"]:
            continue
        for t in dict.fromkeys(tokens(s["term"])):
            o = out.setdefault(t, {"names": 0, "pass": 0, "n": 0, "misread_n": 0, "excluded": 0})
            o["names"] += 1
            o["pass"] += s["pass"]
            o["n"] += s["n"]
            o["misread_n"] += s.get("misread_n", 0)
            o["excluded"] += bool(s["excluded"])
    return out


def generate(models: list[str], out_dir: Path, timeout: float = 300, tries: int = 3, prompt: str = GEN_PROMPT) -> list[Path]:
    """모델마다 새 격리 프로세스 하나 = 묶음 하나. gpt-*는 workflow-runner OMP 실행기, 나머지는 claude -p.
    gpt 실행기가 자주 'prompt did not complete'로 끝나므로 묶음마다 tries번까지 다시 시도한다."""
    import collect_samples as cs  # noqa: F401 — RUNNER 경로 설정을 재사용
    import plain_runner
    run_gpt = cs.load_adapters().run_agent
    gpt_tail = _load(ROOT / "docs/harness/naming_profile.json")["generator"].get("gpt_tail", "")

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, m in enumerate(models, 1):
        p = out_dir / f"batch{i:02d}_{m}.json"
        if p.exists():  # 이어받기
            paths.append(p)
            continue
        for k in range(tries):
            art = out_dir / f"art_batch{i:02d}_{k}"
            if m.startswith("gpt"):  # 동봉 실행기 제약: 형식 요구는 gpt에만 붙인다
                r = run_gpt({}, prompt + gpt_tail, timeout, None, lambda: False, art)
                cands = parse_candidates(r.get("output")) if r.get("status") == "succeeded" else []
            else:  # 평문 생성(plain_runner)
                try:
                    r = {"status": "succeeded"}
                    cands = parse_candidates(plain_runner.claude_text(prompt, m, timeout, art))
                except Exception as exc:  # noqa: BLE001
                    r, cands = {"status": f"failed: {type(exc).__name__}"}, []
            if cands:
                break
        p.write_text(json.dumps({"model": m, "status": r.get("status"), "candidates": cands}, ensure_ascii=False,
                                indent=1), encoding="utf-8")
        print(f"묶음 {i} {m}: {r.get('status')} 후보 {len(cands)}개", flush=True)
        paths.append(p)
    return paths


def load_batches(paths) -> list[list[str]]:
    return [[c["name"] for c in json.loads(Path(p).read_text(encoding="utf-8")).get("candidates", [])] for p in paths]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[0] == "generate":
        prompt = GEN_PROMPT
        if "--brief" in a:  # 다른 주제: 프로필 틀 + 그 브리프
            prompt = gen_prompt(_load(Path(a[a.index("--brief") + 1])), _load(ROOT / "docs/harness/naming_profile.json"))
        generate(a[1].split(","), Path(a[2]), prompt=prompt)
    elif a[0] == "stats":
        batches = load_batches(a[1:])
        st = keyword_stats(batches)
        print(f"묶음 {len(batches)}개, 후보 {sum(map(len, batches))}개(서로 다른 이름 {len({n for b in batches for n in b})}개), 키워드 {len(st)}개")
        print("키워드 | 묶음 등장 | 이름 수 | 예")
        for t, s in ranked(st):
            if s["batches"] >= 2 or s["count"] >= 3:
                print(f'{t} | {s["batches"]}/{len(batches)} | {s["count"]} | {", ".join(s["names"][:3])}')
        print("\n함께 자주 쓰인 쌍:", ", ".join(f"{x}+{y} {k}" for (x, y), k in pairs(batches).most_common(10) if k >= 2))
    elif a[0] == "diversity":
        by = {}
        for p in a[1:]:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            if d.get("candidates"):
                by.setdefault(d.get("model", "?"), []).append([c["name"] for c in d["candidates"]])
        print("생성자 | 묶음 | 서로 다른 이름 | 서로 다른 키워드 | 다른 생성자에 없는 키워드 | 묶음 간 겹침(Jaccard)")
        for s, v in diversity(by).items():
            print(f'{s} | {v["batches"]} | {v["names"]} | {v["distinct_tokens"]} | {v["unique_tokens"]} | {v["within_overlap"]:.2f}')
    elif a[0] == "risk":
        import check_terms as ct

        rules = ct.load_rules(Path(a[a.index("--rules") + 1]))
        i = a.index("--samples") + 1
        files = []
        while i < len(a) and not a[i].startswith("--"):
            files.append(Path(a[i]))
            i += 1
        res = ct.score(rules, files, allow_stale="--allow-stale" in a)
        print("키워드 | 이름 수 | 통과 | 오독률 | 제외된 이름")
        for t, o in sorted(token_outcomes(res).items(), key=lambda kv: (kv[1]["misread_n"] / kv[1]["n"], -kv[1]["pass"] / kv[1]["n"])):
            print(f'{t} | {o["names"]} | {o["pass"]}/{o["n"]} | {o["misread_n"]}/{o["n"]} ({o["misread_n"] / o["n"]:.0%}) | {o["excluded"]}')


if __name__ == "__main__":
    main()
