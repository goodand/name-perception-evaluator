"""용어 설명 규칙 판정.

사용: python scripts/check_terms.py <round.json> [terms.yaml]
      python scripts/check_terms.py --rules <rules.yaml|json> --samples <파일…> [--allow-stale] [--allow-legacy] [--lint]
             [--risky <risky_tokens.json>]
round.json: [{"id": "T01", "term": "...", "explanation": "..."}]
판정: must의 모든 그룹에서 단어가 하나 이상 나오고, must_not이 하나도 없으면 PASS.
비교는 소문자·공백 제거 후 부분 문자열. 그룹은 단어 목록 또는 {label, any}(사유에 이름표).
선택 필드 misread_as {분야: [신호어]}: 신호가 나오면 실패 사유 misread:<분야>. 표본 하나라도 오독이면 그 이름은 제외(게이트).
선택: 제외 안 된 이름 중 통과율 최고, 동점이면 baseline: true 유지(workflow-runner choose와 같음).
LLM 판정은 쓰지 않는다. 설계: docs/harness/name_harness_v2.md (v2.2)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

JUDGE_VERSION = "2"  # normalize·judge를 바꾸면 올린다 → 옛 표본이 stale로 걸러짐
# misread_as는 선택 필드: 없는 규칙의 해시·판정은 v2.1과 같으므로 버전을 올리지 않는다(tests/test_check_terms_gate.py)
RISKY_DEFAULT = Path(__file__).parents[1] / "docs/harness/risky_tokens.json"


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s.lower())


def _groups(rule: dict) -> list[tuple[str | None, list[str]]]:
    return [(g.get("label"), g["any"]) if isinstance(g, dict) else (None, g) for g in rule.get("must", [])]


def judge(expl: str, rule: dict) -> tuple[bool, list[str]]:
    text = norm(expl)
    why = []
    for label, words in _groups(rule):
        if not any(norm(w) in text for w in words):
            why.append(("누락" if label is None else f"누락[{label}]") + ": " + "|".join(words[:4]))
    for w in rule.get("must_not", []):
        if norm(w) in text:
            why.append("오해 신호: " + w)
    why += [f"misread:{field}: {w}" for field, w in misread_hits(text, rule)]
    return (not why), why


def misread_hits(text: str, rule: dict) -> list[tuple[str, str]]:
    """정규화된 설명에 나온 (분야, 첫 신호어). 분야 이름순, 분야당 하나.
    보수적: 부정문("SQL JOIN과는 다르다")도 걸린다 → 제외 근거 원문을 남겨 사람이 확인."""
    hits = []
    for field, words in sorted(rule.get("misread_as", {}).items()):
        w = next((w for w in words if norm(w) in text), None)
        if w is not None:
            hits.append((field, w))
    return hits


def rule_hash(rule: dict) -> str:
    must = sorted(sorted(words) for _, words in _groups(rule))
    key = {"term": rule["term"], "must": must, "must_not": sorted(rule.get("must_not", [])), "judge": JUDGE_VERSION}
    if rule.get("misread_as"):  # 비어 있으면 키를 넣지 않음 → 기존 규칙 해시 유지
        key["misread_as"] = {k: sorted(v) for k, v in rule["misread_as"].items()}
    return hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def load_rules(path: Path) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    if Path(path).suffix in (".yaml", ".yml"):
        import yaml  # 규칙 파일을 읽을 때만 필요

        data = yaml.safe_load(raw)
    else:
        data = json.loads(raw)
    terms = data["terms"] if isinstance(data, dict) else data
    return {t["id"]: t for t in terms}


def to_items(sample) -> list | None:
    """표본 하나 → 항목 목록. 실패 표본은 None."""
    if isinstance(sample, list):
        return sample
    if not isinstance(sample, dict):
        return None
    if sample.get("format") == "samples/v2":
        return sample["items"] if sample.get("status") == "ok" else None
    if "status" in sample:
        out = sample.get("output")
        return out.get("items") if sample["status"] == "succeeded" and isinstance(out, dict) else None
    return sample.get("items")


def legacy_samples(data) -> list:
    """봉투 없는 옛 표본 파일: [표본…] 또는 {모델이름: 표본, note: …}."""
    if isinstance(data, dict):
        return [v for v in data.values() if isinstance(v, list)]
    return [to_items(s) for s in data]


def _read(path: Path) -> list[tuple[str, dict | None, list | None]]:
    """(종류, 봉투, 항목) 목록. 종류: v2 | legacy."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except ValueError:
        data = None
    if data is None or (isinstance(data, dict) and data.get("format") == "samples/v2"):
        envs = [json.loads(x) for x in text.splitlines() if x.strip()] if data is None else [data]
        return [("v2", e, to_items(e)) for e in envs]
    return [("legacy", None, s) for s in legacy_samples(data)]


def score(rules: dict, files: list, allow_stale: bool = False, allow_legacy: bool = False, env_filter=None) -> dict:
    """env_filter(봉투 dict) → bool: 답변자 재실험용(예: 특정 instr_sha만). legacy 표본은 {}로 넘긴다."""
    res = {rid: {"term": r["term"], "pass": 0, "n": 0, "failed": 0, "stale": 0, "legacy": 0, "mismatch": 0,
                 "duplicate": 0, "contrast": {}, "fails": [], "misread": {}, "misread_examples": [], "misread_n": 0,
                 "excluded": False, "baseline": bool(r.get("baseline"))} for rid, r in rules.items()}
    for f in files:
        for kind, e, items in _read(f):
            if env_filter is not None and not env_filter(e or {}):
                continue
            if items is None:
                for rid in (e or {}).get("rule_hashes", {}):
                    if rid in res:
                        res[rid]["failed"] += 1
                continue
            seen = {}
            for it in items:
                seen[(it.get("id"), it.get("term"))] = seen.get((it.get("id"), it.get("term")), 0) + 1
            for it in items:
                rid, term = it.get("id"), it.get("term")
                if rid not in rules:
                    continue
                s, rule = res[rid], rules[rid]
                contrast = kind == "v2" and e.get("role") == "contrast"
                if seen[(rid, term)] > 1:
                    s["duplicate"] += 1  # 표본당 1번만 세고 나머지 사본은 건너뜀
                    seen[(rid, term)] = -1
                    continue
                if seen[(rid, term)] < 0:
                    continue
                if kind == "legacy":
                    s["legacy"] += 1
                    if not allow_legacy:
                        continue
                elif e.get("rule_hashes", {}).get(rid) != rule_hash(rule):
                    s["stale"] += 1
                    if not allow_stale:
                        continue
                ok, why = judge(it.get("explanation", ""), rule)
                if contrast:
                    c = s["contrast"].setdefault(term, [0, 0])
                    c[0] += ok
                    c[1] += 1
                    continue
                if term != rule["term"]:
                    s["mismatch"] += 1
                    continue
                s["pass"] += ok
                s["n"] += 1
                fields = [fd for fd, _ in misread_hits(norm(it.get("explanation", "")), rule)]
                for fd in fields:
                    s["misread"][fd] = s["misread"].get(fd, 0) + 1
                if fields:
                    s["misread_n"] += 1  # 오독률 분자: 분야 수가 아니라 오독이 난 표본 수
                    s["misread_examples"].append(it.get("explanation", ""))
                if not ok:
                    s["fails"].append(f'{it.get("explanation", "")[:60]}… [{"; ".join(why)}]')
    for s in res.values():
        s["excluded"] = bool(s["misread"])  # 게이트: 표본 하나라도 오독이면 제외
    return res


def overlap(rules: dict, files: list, allow_stale: bool = False) -> dict:
    """한 묶음 이름끼리 뜻 겹침: 이름 A의 설명문이 다른 이름 B의 must를 모두 채우면 A→B 1회.
    각 이름이 의도대로 읽혀도 서로 같은 뜻으로 읽히는 쌍을 잡는다. must 없는 이름은 비교 대상에서 뺀다."""
    others = {rid: [ws for _, ws in _groups(r)] for rid, r in rules.items() if r.get("must")}
    res = {rid: {"term": r["term"], "n": 0, "with": {}, "examples": {}} for rid, r in rules.items()}
    for f in files:
        for kind, e, items in _read(f):
            if items is None or kind == "legacy" or e.get("role") == "contrast":
                continue
            for it in items:
                rid = it.get("id")
                if rid not in rules or it.get("term") != rules[rid]["term"]:
                    continue
                if not allow_stale and e.get("rule_hashes", {}).get(rid) != rule_hash(rules[rid]):
                    continue
                s, text = res[rid], norm(it.get("explanation", ""))
                s["n"] += 1
                for oid, groups in others.items():
                    if oid != rid and all(any(norm(w) in text for w in ws) for ws in groups):
                        s["with"][oid] = s["with"].get(oid, 0) + 1
                        s["examples"].setdefault(oid, it.get("explanation", ""))
    return res


def overlap_pairs(ov: dict, rules: dict) -> list[tuple[str, str, int, int]]:
    """(A, B, A가 B로 읽힌 표본 수, A 표본 수), 많은 순."""
    pairs = [(s["term"], rules[o]["term"], k, s["n"]) for s in ov.values() for o, k in s["with"].items()]
    return sorted(pairs, key=lambda x: -x[2] / max(x[3], 1))


# 원문 복사: D:/web_chat_gpt/workflow-runner/runner.py choose() (sha256 a1156710ccf3…ae4, 2026-11-04)
# 수정 프로토콜의 선택 규칙과 같게 하려고 바꾸지 않고 옮겼다. 시험: workflow-runner tests_runner.test_comparison_ties_keep_baseline
def _runner_choose(results):
    """Compare only same-contract trials. Ties preserve the baseline."""
    if not results or len({r['contract_hash'] for r in results})!=1:raise ValueError('Comparison contracts differ')
    if len({r['candidate'] for r in results})!=len(results):raise ValueError('Duplicate candidate')
    for r in results:
        if type(r.get('total'))!=int or r['total']<=0 or type(r.get('passed'))!=int or not 0<=r['passed']<=r['total']:raise ValueError('Invalid comparison counts')
        if not isinstance(r.get('required_gates'),dict) or any(type(v)!=bool for v in r['required_gates'].values()):raise ValueError('Invalid gates')
    if len({tuple(sorted(r['required_gates'])) for r in results})!=1:raise ValueError('Gate sets differ')
    eligible=[r for r in results if r.get('required_gates') and all(v is True for v in r['required_gates'].values())]
    if not eligible:return {'selected':None,'reason':'No candidate passes mandatory gates'}
    best=max(eligible,key=lambda r:(r['passed']/r['total'],r.get('baseline',False)))
    return {'selected':best['candidate'],'reason':'Mandatory gates, then fixture pass rate; ties retain baseline','scope':'Only the declared comparison contract'}


def choose(res: dict, contract: str = "rules") -> dict:
    """score() 결과 → _runner_choose 입력. 게이트 = 오독 없음. 표본 0개 이름은 뺌. 동점·baseline 없으면 id 순 첫째.
    예비 선택(사용자, 2026-11-04): 게이트를 통과한 이름이 없으면 오독률이 가장 낮은 이름들만 남겨 같은 규칙으로 고른다."""
    sampled = [s for _, s in sorted(res.items()) if s["n"] > 0]
    if not sampled:
        return {"selected": None, "reason": "No sampled candidate", "fallback": False}

    def run(group, gate):
        return _runner_choose([{"candidate": s["term"], "contract_hash": contract, "total": s["n"], "passed": s["pass"],
                                "required_gates": {"no_misread": gate(s)}, "baseline": s["baseline"]} for s in group])

    out = run(sampled, lambda s: not s["excluded"])
    if out["selected"] is not None:
        return {**out, "fallback": False}
    low = min(s["misread_n"] / s["n"] for s in sampled)
    out = run([s for s in sampled if s["misread_n"] / s["n"] == low], lambda s: True)
    return {**out, "fallback": True, "reason": f"게이트 통과 후보 없음 → 오독률 최저({low:.0%}) 중에서 " + out["reason"]}


def split_scores(rules: dict, files: list, key: str, allow_stale: bool = False, allow_legacy: bool = False) -> dict:
    """답변자 재실험: 봉투의 key(instr_sha·backend 등) 값마다 따로 score. 봉투가 없거나 key가 없으면 'legacy'."""
    groups = []
    for f in files:
        for _, e, _ in _read(f):
            g = (e or {}).get(key, "legacy")
            if g not in groups:
                groups.append(g)
    return {g: score(rules, files, allow_stale, allow_legacy, env_filter=lambda e, g=g: e.get(key, "legacy") == g)
            for g in groups}


def stability(groups: dict) -> dict:
    """이름별 그룹 판정 (통과, 표본, 제외). 표본 없는 그룹은 뺀다. 제외 여부가 그룹마다 다르면 consistent=False."""
    rids = {rid for res in groups.values() for rid in res}
    out = {}
    for rid in sorted(rids):
        cells = {g: (res[rid]["pass"], res[rid]["n"], res[rid]["excluded"])
                 for g, res in groups.items() if rid in res and res[rid]["n"] > 0}
        out[rid] = {"groups": cells, "consistent": len({c[2] for c in cells.values()}) <= 1}
    return out


def evaluate_variants(variants: dict, files: list) -> dict:
    """평가자 재실험: 같은 답변 묶음에 규칙 변형 {이름: rules} 여러 개. 호출 없음.
    변형마다 해시가 달라도 같은 답변을 다시 판정해야 하므로 stale은 허용하고, (id, term) 짝 검사는 그대로 둔다."""
    terms = {vid: {rid: r["term"] for rid, r in rules.items()} for vid, rules in variants.items()}
    if len({json.dumps(t, sort_keys=True, ensure_ascii=False) for t in terms.values()}) != 1:
        raise ValueError("변형끼리 id·이름이 다르면 비교하지 않는다")
    by = {vid: score(rules, files, allow_stale=True) for vid, rules in variants.items()}
    selected = {vid: choose(res)["selected"] for vid, res in by.items()}
    rids = next(iter(terms.values()))
    # 민감 = '고를 수 있는가'(제외 안 됨 그리고 통과 1개 이상)가 변형마다 다름. 모두 통과 0이면 민감 아님
    sensitive = {rid: len({(not res[rid]["excluded"]) and res[rid]["pass"] > 0
                           for res in by.values() if res[rid]["n"] > 0}) > 1 for rid in rids}
    return {"by_variant": by, "selected": selected, "sensitive": sensitive,
            "selection_sensitive": len(set(selected.values())) > 1}


def lint_rules(rules: dict) -> list[str]:
    """must 그룹에 영문 표기가 하나도 없거나 한글이 하나도 없으면 경고(한영 누락 후보)."""
    warns = []
    for rid, r in rules.items():
        for label, words in _groups(r):
            han = any(re.search("[가-힣]", w) for w in words)
            lat = any(re.search("[a-z]", w.lower()) for w in words)
            if han != lat:
                warns.append(f"{rid} 그룹 {label or words[:3]}: {'영문' if han else '한글'} 표기 없음")
    return warns


def wilson_upper(k: int, n: int, z: float = 1.96) -> float:
    """비율 k/n의 Wilson 95% 상한. 0/6이어도 0.39 — 오독 0회의 남은 위험(게이트에는 쓰지 않음)."""
    if n == 0:
        return 1.0
    p = k / n
    return min(1.0, (p + z * z / (2 * n) + z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n))


CONTEXT_FIELDS = ("purpose", "human_actions", "distinct_from", "role")


def lint_context(rules: dict) -> list[str]:
    """평가자 맥락 필드 검사. 판정·해시에는 쓰지 않는다(답변자에게도 보내지 않음: collect_samples는 id·term만).
    - purpose 비었음, human_actions가 [명사, 술어] 1~3쌍이 아님
    - distinct_from {이웃 개념: 이를 잡는 misread_as 분야 또는 contrasts 이름} 의 대상이 없으면 '근거 없음'
    - misread_as 분야가 distinct_from 어디에도 안 나오면 '출처 없음'
    맥락 필드를 하나도 안 쓴 규칙은 건너뛴다(옛 규칙 파일 소음 방지)."""
    warns = []
    for rid, r in rules.items():
        if not any(f in r for f in CONTEXT_FIELDS):
            continue
        if not str(r.get("purpose", "")).strip():
            warns.append(f"{rid} purpose 비었음")
        acts = r.get("human_actions")
        def _ok(a):  # 삼중항 {actor, action, object} 또는 옛 쌍 [대상, 행동]
            if isinstance(a, dict):
                return all(isinstance(a.get(k), str) and a[k].strip() for k in ("actor", "action", "object"))
            return isinstance(a, list) and len(a) == 2 and all(isinstance(x, str) and x.strip() for x in a)
        if not (isinstance(acts, list) and 1 <= len(acts) <= 3 and all(_ok(a) for a in acts)):
            warns.append(f"{rid} human_actions는 1~3개의 {{actor, action, object}}(또는 [명사, 술어])여야 함: {acts!r}")
        dist = r.get("distinct_from", {}) or {}
        targets = set(r.get("misread_as", {}) or {}) | set(r.get("contrasts", []) or [])
        for concept, via in dist.items():
            if via not in targets:
                warns.append(f'{rid} distinct_from "{concept}" → "{via}": misread_as 분야·contrasts에 근거 없음')
        for field in r.get("misread_as", {}) or {}:
            if field not in dist.values():
                warns.append(f'{rid} misread_as 분야 "{field}": distinct_from에 출처 없음')
    return warns


MAX_KEYWORDS = 3  # 사용자(2026-11-04): "이름에서 키워드가 4개면 긴 편인 것 같아"


def lint_names(rules: dict, risky: dict) -> list[str]:
    """이름 조각(-, _ 기준, 소문자)이 다른 분야 뜻이 강한 단어 사전에 있거나, 조각이 4개 이상이면 수집 전에 경고(비차단)."""
    warns = []
    for rid, r in rules.items():
        toks = [t for t in re.split(r"[-_]", r["term"].lower()) if t]
        for tok in toks:
            if tok in risky:
                warns.append(f'{rid} {r["term"]}: "{tok}" → {risky[tok]}')
        if len(toks) > MAX_KEYWORDS:
            warns.append(f'{rid} {r["term"]}: 길이 — 키워드 {len(toks)}개(긴 편, {MAX_KEYWORDS}개 이하 권장)')
    return warns


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if "--samples" not in args:
        if len(args) < 2:
            raise SystemExit("사용: check_terms.py <답변.json> <규칙 파일(rules.json|names.yaml)> — 규칙 파일을 주세요")
        rnd = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        rules = load_rules(Path(args[1]))
        fails = 0
        for r in rnd:
            ok, why = judge(r["explanation"], rules[r["id"]])
            fails += not ok
            print(f'{r["id"]} {"PASS" if ok else "FAIL"} | {r["term"]} | {"; ".join(why)}')
        print(f"합계: {len(rnd) - fails}/{len(rnd)} 통과")
        return
    rules = load_rules(Path(args[args.index("--rules") + 1]))
    i = args.index("--samples") + 1
    files = []
    while i < len(args) and not args[i].startswith("--"):
        files.append(Path(args[i]))
        i += 1
    if "--lint" in args:
        for w in lint_rules(rules):
            print("lint:", w)
        for w in lint_context(rules):
            print("lint-context:", w)
        risky = Path(args[args.index("--risky") + 1]) if "--risky" in args else RISKY_DEFAULT
        if risky.exists():
            for w in lint_names(rules, json.loads(risky.read_text(encoding="utf-8"))):
                print("lint-name:", w)
    res = score(rules, files, "--allow-stale" in args, "--allow-legacy" in args)
    for rid, s in res.items():
        skip = ", ".join(f"{k} {s[k]}" for k in ("failed", "stale", "legacy", "mismatch", "duplicate") if s[k])
        con = ", ".join(f"대조 {t} {p}/{n}" for t, (p, n) in s["contrast"].items())
        gate = ""
        if s["excluded"]:
            mis = ", ".join(f"오독 {fd} {k}" for fd, k in sorted(s["misread"].items()))
            rate = f'오독률 {s["misread_n"]}/{s["n"]} ({s["misread_n"] / s["n"]:.0%})'
            gate = f" | 제외: {rate}, {mis} | 근거: " + " / ".join(x[:80] for x in s["misread_examples"][:2])
        elif s["n"] and any(r.get("misread_as") for r in rules.values()):
            gate = f' | 오독 0/{s["n"]} (95% 상한 {wilson_upper(0, s["n"]):.0%})'
        print(f'{rid} {s["pass"]}/{s["n"]} {s["term"]}' + (f" ({skip})" if skip else "") + (f" | {con}" if con else "")
              + gate + ("" if not s["fails"] else " | " + " / ".join(s["fails"])))
    sel = choose(res, str(sorted(rule_hash(r) for r in rules.values())))
    print(f'\n{"예비 선택" if sel.get("fallback") else "선택"}: {sel["selected"] or "없음"} ({sel["reason"]})')
    if "--by" in args:  # 답변자 재실험: 지시문(instr_sha)·백엔드별
        key = args[args.index("--by") + 1]
        groups = split_scores(rules, files, key, "--allow-stale" in args, "--allow-legacy" in args)
        print(f"\n답변자 재실험: {key}별 (통과/표본, 제외=X). 그룹 {len(groups)}개: {', '.join(groups)}")
        for rid, st in stability(groups).items():
            cells = " | ".join(f"{g} {p}/{n}{' X' if x else ''}" for g, (p, n, x) in st["groups"].items())
            print(f'{rid} {rules[rid]["term"]}: {cells}' + ("" if st["consistent"] else "  ← 지시문 취약(게이트 판정 갈림)"))
    if "--variants" in args:  # 평가자 재실험: 같은 답변에 규칙 변형
        j = args.index("--variants") + 1
        vfiles = []
        while j < len(args) and not args[j].startswith("--"):
            vfiles.append(Path(args[j]))
            j += 1
        variants = {"기준": rules, **{p.stem: load_rules(p) for p in vfiles}}
        ev = evaluate_variants(variants, files)
        print(f"\n평가자 재실험: 규칙 변형 {len(variants)}개 ({', '.join(variants)}), 같은 답변 재판정")
        for rid in rules:
            cells = " | ".join(f'{v} {r[rid]["pass"]}/{r[rid]["n"]}{" X" if r[rid]["excluded"] else ""}'
                               for v, r in ev["by_variant"].items())
            print(f'{rid} {rules[rid]["term"]}: {cells}' + ("  ← 규칙 민감" if ev["sensitive"][rid] else ""))
        print("변형별 선택: " + ", ".join(f"{v}={s}" for v, s in ev["selected"].items())
              + ("  ← 선택이 규칙에 따라 갈림" if ev["selection_sensitive"] else ""))


if __name__ == "__main__":
    main()
