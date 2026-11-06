"""명명 검증을 한 번에 돌린다 — Claude 모델만으로 동작 (하네스 v2.2).

사용: python scripts/run_naming.py <brief.json> <후보: 쉼표 목록 또는 한 줄에 하나인 .txt> <out_dir>
      [--rounds N] [--human] [--no-network] [--profile docs/harness/naming_profile.json]
흐름: 프로필(주제 무관 기준) + 브리프(주제별 평가자 맥락) + 후보
  → 규칙 생성(out/rules.json) → 사전 검사(맥락·위험 단어·길이) → 충돌 조회(참고)
  → 답변 수집(모델별 폴더, 독자가 사람이거나 --human이면 사람 관점 추가)
  → 오독 게이트 판정 → 선택(게이트 → 통과율 → 기존안 유지, 전부 제외면 오독률 최저 예비 선택) → out/report.md
답변자에게는 이름만 간다(collect_samples). 브리프·프로필 내용은 평가자 쪽에만 쓴다.
안내: docs/harness/NAMING_GUIDE.md
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_terms as ct  # noqa: E402
import collect_samples as cs  # noqa: E402
import collect_variants as cv  # noqa: E402

ROOT = Path(__file__).parents[1]
PROFILE_DEFAULT = ROOT / "docs/harness/naming_profile.json"
CONTEXT_KEYS = ("purpose", "human_actions", "distinct_from", "role", "audience", "misread_as", "must")


def build_rules(brief: dict, names: list[str]) -> dict:
    rules = {}
    for i, n in enumerate(names, 1):
        r = {"id": f"C{i:02d}", "term": n, **{k: brief[k] for k in CONTEXT_KEYS if k in brief},
             "must_not": list(brief.get("must_not", []))}
        if i == 1 and brief.get("contrasts"):  # 대조 이름은 규칙 하나에만 달아 한 번만 수집
            r["contrasts"] = list(brief["contrasts"])
        rules[r["id"]] = r
    return rules


def perspectives(brief: dict, profile: dict, force_human: bool = False) -> list[str]:
    human = force_human or brief.get("audience", "developer") != "developer"
    return ["developer"] + (list(profile["perspectives"]["prompts"]) if human else [])


def parse_answerers(spec) -> list[tuple[str, str]]:
    """'claude:haiku,gpt:gpt-6-luna,qwen:<LM Studio 모델 id>' 또는 그 목록 → [(백엔드, 모델)]."""
    items = spec.split(",") if isinstance(spec, str) else spec
    return [tuple(a.strip().split(":", 1)) for a in items if a.strip()]


def _answerers(profile: dict) -> list[tuple[str, str]]:
    return parse_answerers(profile["answerers"]["default"])


def run(profile: dict, brief: dict, names: list[str], out_dir: Path, rounds: int | None = None,
        backend_factory=None, check_network: bool = True, force_human: bool = False, timeout: float = 300, answerers=None,
        reviewer=None, reviewer_factory=None, prompt_reviser=None, slots=None) -> dict:
    """slots: 답변자 지시문 틀의 빈칸 값(외부 에이전트가 JSON으로 줌). 걸리면 prompt_slots.SlotRejected — 걸린 빈칸만 다시 채운다.
    prompt_reviser는 시험용 훅만 남긴다(CLI에서는 쓰지 않음: 지시문을 다시 쓰는 모델은 두지 않는다)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    backend_factory = backend_factory or cs.make_backend
    rounds = rounds or profile["answerers"]["rounds"]
    rules = build_rules(brief, names)
    rules_path = out_dir / "rules.json"
    rules_path.write_text(json.dumps({"terms": list(rules.values())}, ensure_ascii=False, indent=1), encoding="utf-8")

    lint = ct.lint_context(rules)
    views = perspectives(brief, profile, force_human)
    used = answerers or _answerers(profile)
    # 프롬프트 거름 루프: 응답자·평가자에게 갈 지시문을 먼저 검사하고, 걸리면 고쳐 다시 검사. 깨끗해진 것만 보낸다
    import prompt_check
    import review_explanations as re_
    import prompt_slots as ps
    instr, slot_log = cs.INSTR, []
    if slots:
        t = ps.load()
        instr, slot_log = ps.gate(t["templates"]["답변자"], {**t["defaults"]["답변자"], **slots})
        (out_dir / "slot_gate.json").write_text(json.dumps(slot_log, ensure_ascii=False, indent=1), encoding="utf-8")
    want = {"답변자": instr, **{f"관점:{v}": profile["perspectives"]["prompts"][v] for v in views if v != "developer"}}
    if any(k == "gpt" for k, _ in used):
        want["gpt 꼬리"] = cs.GPT_TAIL
        want["gpt 역할"] = cs.GPT_PERSONA
    if reviewer:
        want["평가자"] = re_.INSTR
        want.update({f"평가자 관점:{v}": t for v, t in re_.VIEWS.items()})
    allow = {"gpt 꼬리": ("json", "object")}  # 동봉 gpt 실행기가 이 형식만 받는다(PROVENANCE). 이유를 기록하고 허용
    try:
        clean, gate_log = prompt_check.gate(want, prompt_reviser, allow=allow)
    finally:
        (out_dir / "prompt_gate.json").write_text(json.dumps(locals().get("gate_log", []), ensure_ascii=False, indent=1),
                                                   encoding="utf-8")
    saved = (cs.INSTR, re_.INSTR, dict(re_.VIEWS))
    cs.INSTR = clean["답변자"]
    prompts = {**profile["perspectives"]["prompts"], **{k.split(":", 1)[1]: v for k, v in clean.items() if k.startswith("관점:")}}
    if reviewer:
        re_.INSTR = clean["평가자"]
        re_.VIEWS.update({k.split(":", 1)[1]: v for k, v in clean.items() if k.startswith("평가자 관점:")})
    revised = sorted({g["prompt"] for g in gate_log if g["round"] > 0})
    lint += [f"프롬프트 거름: {', '.join(revised)} 고쳐서 보냄(prompt_gate.json)"] if revised else []
    if ct.RISKY_DEFAULT.exists():
        lint += ct.lint_names(rules, json.loads(ct.RISKY_DEFAULT.read_text(encoding="utf-8")))

    avail = {}
    if check_network:
        import check_availability as ca

        avail = {n: ca.check(n)["overall"] for n in names}

    try:
        return _collect_and_judge(profile, rules, rules_path, names, out_dir, rounds, backend_factory, timeout, used, views,
                                  prompts, lint, avail, reviewer, reviewer_factory)
    finally:
        cs.INSTR, re_.INSTR = saved[0], saved[1]
        re_.VIEWS.clear()
        re_.VIEWS.update(saved[2])


def _collect_and_judge(profile, rules, rules_path, names, out_dir, rounds, backend_factory, timeout, used, views, prompts,
                       lint, avail, reviewer, reviewer_factory):
    import plain_runner

    log = out_dir / "usage.jsonl"
    with plain_runner.usage(log, "첫눈 독자"):
        _collect(rules, rules_path, out_dir, rounds, backend_factory, timeout, used, views, prompts)
    with plain_runner.usage(log, "대조 평가자"):
        return _judge(profile, rules, names, out_dir, timeout, views, lint, avail, reviewer, reviewer_factory, log)


def _collect(rules, rules_path, out_dir, rounds, backend_factory, timeout, used, views, prompts):
    for kind, model in used:
        d = out_dir / model.replace("/", "_")  # 모델별 폴더: 같은 폴더면 이어받기가 다른 모델 표본을 건너뛴다
        d.mkdir(exist_ok=True)
        call = backend_factory(kind, model, d / "art")
        for v in views:
            if v == "developer":
                cs.collect(call, rules, str(rules_path), rounds, d / "developer.jsonl", model, kind, timeout)
            else:
                cv.collect_variant(call, v, prompts[v], rules, str(rules_path), rounds, d, model, kind, timeout)


def _judge(profile, rules, names, out_dir, timeout, views, lint, avail, reviewer, reviewer_factory, log):
    files = sorted(out_dir.glob("*/*.jsonl"))
    res = ct.score(rules, files)
    sel = ct.choose(res, str(sorted(ct.rule_hash(r) for r in rules.values())))
    warnings = []
    chosen = next((s for s in res.values() if s["term"] == sel["selected"]), None)
    floor = profile.get("warn_below_pass_rate", 0.5)
    if chosen and chosen["n"] and chosen["pass"] / chosen["n"] < floor:  # 다른 후보가 모두 제외되면 통과 0도 뽑힌다
        warnings.append(f'선택된 {chosen["term"]}의 통과율 {chosen["pass"]}/{chosen["n"]}이 {floor:.0%} 미만: '
                        "표본을 늘리거나 후보를 바꿀 것")
    rev = {}
    if reviewer:  # 격리 평가자: 사람 관점에서 설명문을 다시 본다(경고만). 사람 관점이 있으면 둘 다
        import review_explanations as re_
        kind, model = reviewer
        call = (reviewer_factory or re_.make_reviewer)(kind, model, out_dir / "art_review")
        for v in [v for v in views if v in re_.VIEWS] or ["end_user"]:
            rev.update({f"{rid}:{v}": s for rid, s in re_.review(rules, files, call, v, timeout).items()})
        (out_dir / "review.json").write_text(json.dumps(rev, ensure_ascii=False, indent=1), encoding="utf-8")
    import plain_runner

    cost = plain_runner.summarize(log)
    _report(out_dir / "report.md", rules, res, sel, lint, avail, views, warnings, rev, cost)
    return {"usage": cost, "review": rev, "selected": sel["selected"], "fallback": sel.get("fallback", False), "reason": sel["reason"],
            "warnings": warnings, "scores": res, "lint": lint, "availability": avail, "files": [str(f) for f in files]}


def _report(path: Path, rules: dict, res: dict, sel: dict, lint: list, avail: dict, views: list,
            warnings: list = (), rev: dict | None = None, cost: dict | None = None) -> None:
    gate = [w for w in lint if w.startswith("프롬프트 거름")]
    lines = ["# 명명 검증 결과", "", f"관점: {', '.join(views)}", "",
             f"프롬프트 거름: {gate[0] if gate else '통과(고침 없음)'} — 걸린 지시문은 고쳐 다시 검사한 뒤에만 보냄", "",
             "| 이름 | 통과 | 오독률 | 제외 | 충돌(참고) | 오독 근거 |", "|---|---|---|---|---|---|"]
    for rid, s in res.items():
        rate = f'{s["misread_n"]}/{s["n"]}' if s["n"] else "-"
        ev = (s["misread_examples"][0][:80].replace("|", "/") if s["misread_examples"] else "")
        lines.append(f'| {s["term"]} | {s["pass"]}/{s["n"]} | {rate} | {"제외" if s["excluded"] else ""} '
                     f'| {avail.get(s["term"], "-")} | {ev} |')
    lines += ["", f'**{"예비 선택" if sel.get("fallback") else "선택"}: {sel["selected"] or "없음"}** ({sel["reason"]})',
              *[f"> 경고: {w}" for w in warnings],
              "", "판정 뒤 설명문을 직접 읽어 교차 확인할 것(규칙은 쉬운 말 표현을 놓칠 수 있다).", "", "## 사전 검사"]
    lines += [f"- {w}" for w in lint] or ["- 없음"]
    if rev:
        import review_explanations as re_
        lines += re_.report_lines(rev)
    if cost:
        lines += ["", "## 주체별 호출 기록(usage.jsonl)", "", "| 주체 | 호출 | 시간(초) | 입력 | 출력 | 캐시 읽기 | 비용(USD) |",
                  "|---|---|---|---|---|---|---|"]
        lines += [f'| {a} | {s["calls"]} | {s["seconds"]} | {s["input"]} | {s["output"]} | {s["cache_read"]} | {s["cost_usd"]} |'
                  for a, s in cost.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    brief = json.loads(Path(a[0]).read_text(encoding="utf-8"))
    src = Path(a[1])
    names = [x.strip() for x in (src.read_text(encoding="utf-8").splitlines() if src.is_file() else a[1].split(","))
             if x.strip()]
    profile = json.loads(Path(a[a.index("--profile") + 1] if "--profile" in a else PROFILE_DEFAULT)
                         .read_text(encoding="utf-8"))
    out = run(profile, brief, names, Path(a[2]), int(a[a.index("--rounds") + 1]) if "--rounds" in a else None,
              check_network="--no-network" not in a, force_human="--human" in a)
    print(Path(a[2]) / "report.md")
    print(f'{"예비 선택" if out["fallback"] else "선택"}: {out["selected"]}')


if __name__ == "__main__":
    main()
