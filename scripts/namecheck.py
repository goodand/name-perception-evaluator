"""namecheck — 이름 검증 하네스의 에이전트용 CLI (하네스 v2.2, Claude 모델만으로 동작).

에이전트(도구를 쓰는 쪽)는 --json으로 받고 종료 코드로 성공/실패를 본다. 사람은 같은 명령의 표 출력이나
run의 report.md를 본다. 반복되고 선택지가 적은 단계는 여기(스크립트)에, 창의·관점 의존 단계는 스킬에 둔다.
안내: docs/harness/NAMING_GUIDE.md
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import check_terms as ct  # noqa: E402
import name_keywords as nk  # noqa: E402

ROOT = Path(__file__).parents[1]
PROFILE = ROOT / "docs/harness/naming_profile.json"
AUDIENCES = ("developer", "end-user", "mixed")
NAME_RE = {"-": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"), "_": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")}


def _load(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def _names(arg: str) -> list[str]:
    p = Path(arg)
    src = p.read_text(encoding="utf-8").splitlines() if p.is_file() else arg.split(",")
    return [x.strip() for x in src if x.strip()]


def check_brief(b: dict) -> list[str]:
    """브리프(빈칸에 들어갈 값)의 자료형·형식 검사. 허용 값 목록이 아니라 형식만 강제한다."""
    e = []
    if not (isinstance(b.get("purpose"), str) and b["purpose"].strip()):
        e.append("purpose: 비어 있지 않은 문장이어야 함")
    acts = b.get("human_actions")
    if not (isinstance(acts, list) and 1 <= len(acts) <= 3):
        e.append("human_actions: 1~3개의 {actor, action, object} 삼중항이어야 함")
    else:
        for i, a in enumerate(acts):
            if not isinstance(a, dict) or not all(isinstance(a.get(k), str) and a[k].strip()
                                                  for k in ("actor", "action", "object")):
                e.append(f"human_actions[{i}]: actor·action·object가 모두 있어야 함(주체-행동-대상): {a!r}")
    if b.get("audience") not in AUDIENCES:
        e.append(f"audience: {'|'.join(AUDIENCES)} 중 하나여야 함")
    if not isinstance(b.get("distinct_from"), dict) or not b.get("distinct_from"):
        e.append("distinct_from: {혼동 금지 이웃 개념: 그것을 잡는 misread_as 분야 또는 contrasts 이름} 이어야 함")
    if not isinstance(b.get("must"), list) or not b.get("must"):
        e.append("must: 판정 그룹 목록이 있어야 함")
    if b.get("misread_as") is not None and not isinstance(b["misread_as"], dict):
        e.append("misread_as: {분야: [신호어]} 이어야 함")
    return e


def filter_names(names: list[str], max_keywords: int, sep: str = "-") -> tuple[list[str], list[list[str]]]:
    """생성 결과 이름을 형식으로 거른다. 탈락은 [이름, 사유]로 남긴다."""
    kept, dropped = [], []
    for n in names:
        if not NAME_RE[sep].match(n):
            dropped.append([n, f"형식: 영어 소문자·숫자 단어를 '{sep}'로 이어야 함"])
        elif len(n.split(sep)) > max_keywords:
            dropped.append([n, f"키워드 {len(n.split(sep))}개(최대 {max_keywords})"])
        else:
            kept.append(n)
    return kept, dropped


def _emit(obj, as_json: bool, text: str = "") -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1) if as_json else text)


def cmd_brief_check(a):
    errs = check_brief(_load(a.brief))
    _emit({"ok": not errs, "errors": errs}, a.json, "\n".join(errs) or "브리프 형식 OK")
    return 1 if errs else 0


def cmd_lint(a):
    import run_naming as rn

    prof = _load(PROFILE)
    kept, dropped = filter_names(_names(a.names), prof["max_keywords"], a.sep)
    rules = rn.build_rules(_load(a.brief), kept)
    warns = ct.lint_context(rules) + ct.lint_names(rules, _load(ct.RISKY_DEFAULT))
    _emit({"kept": kept, "dropped": dropped, "warnings": warns}, a.json,
          "\n".join([f"탈락 {n}: {r}" for n, r in dropped] + [f"경고 {w}" for w in warns]) or "문제 없음")
    return 0


def cmd_generate(a):
    prof = _load(PROFILE)
    prompt = nk.gen_prompt(_load(a.brief), prof, a.n)
    paths = nk.generate(a.models.split(","), Path(a.out), prompt=prompt)
    batches = nk.load_batches(paths)
    _emit({"batches": [str(p) for p in paths], "counts": [len(b) for b in batches]}, a.json,
          "\n".join(f"{p}: {len(b)}개" for p, b in zip(paths, batches)))
    return 0 if any(batches) else 1


def cmd_availability(a):
    import check_availability as ca

    res = [ca.check(n) for n in _names(a.names)]
    _emit(res, a.json, "\n".join(f'{r["name"]} | {r["overall"]} | pypi={r["pypi"]} npm={r["npm"]} github={r["github"]}'
                                 for r in res))
    return 0


def cmd_run(a):
    import run_naming as rn

    b = _load(a.brief)
    errs = check_brief(b)
    if errs:
        _emit({"ok": False, "errors": errs}, a.json, "\n".join(errs))
        return 1
    prof = _load(PROFILE)
    kept, dropped = filter_names(_names(a.names), prof["max_keywords"], a.sep)
    answerers = rn.parse_answerers(a.answerers) if a.answerers else None
    local = [m for k, m in (answerers or rn._answerers(prof)) if k == "qwen"]
    if local and a.no_local:  # GPU를 다른 세션이 쓸 때: 로컬 LLM은 켜지도 부르지도 않는다
        errs = [f"--no-local인데 로컬 LLM 답변자가 있음: {', '.join(local)} (claude·gpt만 쓸 것)"]
        _emit({"ok": False, "errors": errs}, a.json, errs[0])
        return 1
    if local:
        errs = ensure_lmstudio(local)
        if errs:
            _emit({"ok": False, "errors": errs}, a.json, "\n".join(errs))
            return 1
    out = rn.run(prof, b, kept, Path(a.out), a.rounds, check_network=not a.no_network, force_human=a.human,
                 answerers=answerers, reviewer=tuple(a.review.split(":", 1)) if a.review else None)
    summary = {"selected": out["selected"], "fallback": out["fallback"], "warnings": out["warnings"], "dropped": dropped,
               "report": str(Path(a.out) / "report.md"),
               "names": {s["term"]: {"pass": s["pass"], "n": s["n"], "misread_n": s["misread_n"],
                                     "excluded": s["excluded"], "misread": s["misread"]}
                         for s in out["scores"].values()}}
    _emit(summary, a.json, Path(summary["report"]).read_text(encoding="utf-8"))
    return 0


def cmd_judge(a):
    rules = ct.load_rules(Path(a.rules))
    res = ct.score(rules, [Path(p) for p in a.samples], a.allow_stale, a.allow_legacy)
    sel = ct.choose(res, str(sorted(ct.rule_hash(r) for r in rules.values())))
    obj = {"selected": sel["selected"], "fallback": sel.get("fallback", False), "reason": sel["reason"],
           "names": {s["term"]: {k: s[k] for k in ("pass", "n", "misread_n", "excluded", "misread", "stale", "failed")}
                     for s in res.values()}}
    _emit(obj, a.json, "\n".join(f'{t} {v["pass"]}/{v["n"]} 오독 {v["misread_n"]}{" 제외" if v["excluded"] else ""}'
                                 for t, v in obj["names"].items()) + f'\n선택: {obj["selected"]}')
    return 0


def cmd_compare(a):
    import compare_judges as cj

    old = Path(a.old) if Path(a.old).is_file() else cj.old_judge_from_git(a.old)
    pairs = [(Path(s.split("::", 1)[0]), [Path(x) for x in s.split("::", 1)[1].split(",")]) for s in a.pairs]
    out = cj.compare(old, cj.NEW, pairs)
    _emit(out, a.json, f'판정 줄 {out["total_lines"]}, 다른 줄 {out["diff_lines"]}')
    return 0 if out["diff_lines"] == 0 else 2  # 2 = 차이 있음(판정식을 바꿨다면 정상, 직접 읽어 확인)


def cmd_stats(a):
    batches = nk.load_batches(a.batches)
    st = nk.ranked(nk.keyword_stats(batches))
    _emit([{"keyword": k, **{x: v[x] for x in ("batches", "count")}} for k, v in st], a.json,
          "\n".join(f'{k} {v["batches"]}/{len(batches)} {v["count"]}' for k, v in st))
    return 0


def cmd_risk(a):
    rules = ct.load_rules(Path(a.rules))
    to = nk.token_outcomes(ct.score(rules, [Path(p) for p in a.samples], a.allow_stale))
    _emit(to, a.json, "\n".join(f'{k} 오독 {v["misread_n"]}/{v["n"]} 통과 {v["pass"]}/{v["n"]}' for k, v in to.items()))
    return 0


def cmd_overlap(a):
    rules = ct.load_rules(Path(a.rules))
    pairs = ct.overlap_pairs(ct.overlap(rules, [Path(x) for x in a.samples], a.allow_stale), rules)
    _emit([{"name": x, "read_as": y, "k": k, "n": n} for x, y, k, n in pairs], a.json,
          "\n".join(f"{x} → {y} {k}/{n}: 둘 중 하나를 바꿀 것" for x, y, k, n in pairs) or "겹침 없음")
    return 2 if pairs else 0


LMS_URL = __import__("plain_runner").LMS_BASE + "/v1/models"  # LMSTUDIO_URL 환경 변수로 바꿀 수 있음


def _lms_models():
    """LM Studio 서버에 올라온 모델 id 목록. 서버가 꺼져 있으면 None."""
    import urllib.request

    try:
        with urllib.request.urlopen(LMS_URL, timeout=3) as r:
            return [m["id"] for m in json.load(r)["data"]]
    except Exception:  # noqa: BLE001
        return None


def _lms(*args):
    """lms CLI 실행. CLI가 없으면 None, 있으면 종료 코드."""
    import shutil
    import subprocess

    exe = shutil.which("lms") or next((str(p) for p in (Path.home() / ".lmstudio/bin/lms.exe", Path.home() / ".lmstudio/bin/lms")
                                       if p.is_file()), None)
    if exe is None:
        return None
    if not Path(exe).is_file():
        return None
    return subprocess.run([exe, *args], capture_output=True, text=True, timeout=600).returncode


def ensure_lmstudio(models: list[str]) -> list[str]:
    """서버가 꺼져 있으면 켜고, 없는 모델은 올린다. 남은 문제를 문장 목록으로 돌려준다."""
    if _lms_models() is None:
        if _lms("server", "start") is None:
            return ["lms CLI 없음: LM Studio를 설치하거나 앱에서 서버를 켜 주세요"]
    loaded = _lms_models()
    if loaded is None:
        return ["LM Studio 서버를 켜지 못함(lms server start 실패)"]
    errs = []
    for m in models:
        if m not in loaded and _lms("load", m, "-y") != 0:
            errs.append(f"모델 {m} 올리기 실패(lms ls로 id 확인)")
    return errs


def doctor() -> dict:
    """답변자 백엔드마다 이 PC에서 쓸 수 있는지. 호출은 하지 않고 실행 파일·서버만 본다."""
    import shutil

    import collect_samples as cs

    rep = {}
    c = shutil.which("claude")
    rep["claude"] = {"ok": bool(c), "detail": c or "claude CLI 없음"}
    try:
        adapters = cs.load_adapters()

        exe = Path(adapters._OMP_EXE)
        env_note = " [NAME_HARNESS_OMP_ROOT]" if os.environ.get("NAME_HARNESS_OMP_ROOT") else " (다른 PC면 NAME_HARNESS_OMP_ROOT로 지정)"
        rep["gpt"] = {"ok": exe.is_file(), "detail": f"{exe}{env_note} ({'있음' if exe.is_file() else '없음'}), "
                                                      "실패가 잦으면 다시 run(이어받기)"}
    except Exception as exc:  # noqa: BLE001
        rep["gpt"] = {"ok": False, "detail": f"adapters 읽기 실패: {exc}"}
    ids = _lms_models()
    rep["qwen"] = ({"ok": True, "detail": "LM Studio 서버 켜짐: " + ", ".join(ids)} if ids is not None else
                   {"ok": False, "detail": "LM Studio 서버 꺼짐: run이 qwen 답변자를 쓰면 자동으로 켠다"})
    return rep


def cmd_doctor(a):
    rep = doctor()
    _emit(rep, a.json, "\n".join(f'{k}: {"OK" if v["ok"] else "불가"} - {v["detail"]}' for k, v in rep.items()))
    return 0


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="namecheck", description="이름 검증 하네스 CLI (에이전트는 --json)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        s = sub.add_parser(name, help=help_)
        s.add_argument("--json", action="store_true", help="에이전트용 JSON 출력")
        s.set_defaults(fn=fn)
        return s

    s = add("brief-check", cmd_brief_check, "브리프 형식 검사(삼중항·필수 필드)")
    s.add_argument("brief")
    s = add("generate", cmd_generate, "격리 생성: 모델마다 새 프로세스 한 묶음")
    s.add_argument("models", help="쉼표 목록, 예: haiku,haiku,sonnet")
    s.add_argument("out")
    s.add_argument("--brief", default=str(ROOT / "docs/harness/briefs/name-harness.json"))
    s.add_argument("--n", type=int, default=20)
    s = add("lint", cmd_lint, "후보 형식 거르기 + 위험 단어·길이·맥락 경고(수집 전)")
    s.add_argument("brief")
    s.add_argument("names", help="쉼표 목록 또는 한 줄에 하나인 파일")
    s.add_argument("--sep", default="-", choices=["-", "_"])
    s = add("availability", cmd_availability, "PyPI·npm·GitHub 충돌 조회(참고 정보)")
    s.add_argument("names")
    s = add("run", cmd_run, "브리프+후보 → 수집(Sonnet·Haiku) → 오독 게이트 → 선택 → report.md")
    s.add_argument("brief")
    s.add_argument("names")
    s.add_argument("out")
    s.add_argument("--rounds", type=int)
    s.add_argument("--human", action="store_true", help="사람 관점(UI/UX·최종 사용자) 추가")
    s.add_argument("--no-network", action="store_true")
    s.add_argument("--sep", default="-", choices=["-", "_"])
    s.add_argument("--no-local", action="store_true", help="로컬 LLM(LM Studio) 답변자 금지, 서버도 켜지 않음")
    s.add_argument("--review", help="격리 평가자(경고만), 예: claude:sonnet. 사람 관점(UX·최종 사용자)으로 설명문을 다시 본다")
    s.add_argument("--answerers", help="프로필 기본 대신, 예: claude:haiku,gpt:gpt-6-luna,qwen:qwen/qwen3.8-27b")
    s = add("judge", cmd_judge, "이미 받은 표본을 규칙으로 판정")
    s.add_argument("--rules", required=True)
    s.add_argument("--samples", nargs="+", required=True)
    s.add_argument("--allow-stale", action="store_true")
    s.add_argument("--allow-legacy", action="store_true")
    s = add("compare", cmd_compare, "판정기 기존안(git 커밋 또는 파일) vs 현재, 같은 표본")
    s.add_argument("old")
    s.add_argument("pairs", nargs="+", help="규칙::표본,표본")
    s = add("stats", cmd_stats, "생성 묶음 키워드 통계")
    s.add_argument("batches", nargs="+")
    s = add("risk", cmd_risk, "검증 결과를 키워드별 오독률로")
    s.add_argument("--rules", required=True)
    s.add_argument("--samples", nargs="+", required=True)
    s.add_argument("--allow-stale", action="store_true")
    s = add("overlap", cmd_overlap, "한 묶음 이름끼리 뜻 겹침(A의 설명이 B의 must를 채움). 겹침 있으면 종료 코드 2")
    s.add_argument("--rules", required=True, help="이름마다 자기 must를 가진 규칙 묶음")
    s.add_argument("--samples", nargs="+", required=True)
    s.add_argument("--allow-stale", action="store_true")
    add("doctor", cmd_doctor, "답변자 백엔드(claude·gpt·LM Studio) 사용 가능 여부")
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
