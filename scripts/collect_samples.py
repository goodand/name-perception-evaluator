"""이름·용어 설명 표본 수집 (판정은 check_terms.py).

사용: python scripts/collect_samples.py <qwen|gpt|claude> <model_id> <rules.yaml> <k> <out.jsonl> [--list] [--timeout 초]
- 기본 solo: 이름 하나당 호출 한 번(목록 힌트 차단). --list는 이전 회차 재현용(홀수 회차 순서 뒤집기).
- 규칙의 contrasts(의도와 다르게 읽혀야 할 이름)도 같은 지시문으로 받는다(role=contrast).
- 표본마다 바로 jsonl에 이어 쓰고, 같은 (role, 이름, 회차)의 ok 표본이 있으면 건너뛴다(재개).
- 모든 예외는 failed/timed_out 표본으로 기록하고 계속한다.
설계: docs/harness/name_harness_v2.md (v2.1)
"""
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_terms import load_rules, rule_hash  # noqa: E402

# 답변자 실행기: 환경 변수가 있으면 그 경로, 없으면 저장소 안 동봉본(scripts/vendor/workflow_runner, 원본 수정 없음)
RUNNER = Path(os.environ.get("NAME_HARNESS_RUNNER") or Path(__file__).parent / "vendor" / "workflow_runner")


def load_adapters():
    """동봉 실행기 adapters 모듈. gpt(OMP) 경로가 PC 고정이라 NAME_HARNESS_OMP_ROOT가 있으면 import 뒤 덮어쓴다(동봉본 무수정)."""
    sys.path.insert(0, str(RUNNER))
    import adapters

    root = os.environ.get("NAME_HARNESS_OMP_ROOT")
    if root:
        adapters._OMP_ROOT = Path(root)
        adapters._OMP_EXE = adapters._OMP_ROOT / ("omp.exe" if os.name == "nt" else "omp")
        adapters._CONTROLLED_CONFIG = adapters._OMP_ROOT / "controlled.yml"
    return adapters
# 평문 지시문: 개발·SW 단어와 형식 요구를 넣지 않는다(들어간 단어가 답변을 끌어당긴다). 검사: scripts/prompt_check.py
FRAMING = "이름 하나가 주어집니다. 다른 설명은 없습니다."
CONTRACT = "이 이름을 처음 본 사람이 가장 자연스럽게 떠올릴 뜻을 한국어 1~2문장으로 적어 주세요. 모르면 짐작해서 적고, 뜻만 적어 주세요."
INSTR = f"{FRAMING} {CONTRACT}"
# gpt(동봉 OMP 실행기)는 출력이 이 모양이어야 받는다. 실행기를 고치지 않으므로 gpt에만 붙인다(지시문 검사에서 경고됨)
GPT_PERSONA = ("당신은 사람이 화면에서 읽을 이름과 글을 쓰는 작가입니다. "
               "처음 보는 사람의 눈으로 읽어 주세요.\n\n")  # gpt만: 형식 꼬리(GPT_TAIL)를 희석(사용자 2026-11-06)
GPT_TAIL = '\nReturn only a JSON object {"items":[{"id":"...","term":"...","explanation":"..."}]}.'


def instr_sha() -> str:
    return hashlib.sha256(INSTR.encode("utf-8")).hexdigest()[:12]


def validate(raw, names: list[dict]) -> tuple[str, list, str]:
    """(status, items, error). 요청한 (id, term)이 정확히 한 번씩, 설명이 비지 않아야 ok."""
    if isinstance(raw, dict) and "status" in raw:
        if raw["status"] != "succeeded" or not isinstance(raw.get("output"), dict):
            return "failed", [], f'adapter {raw["status"]}: {str(raw.get("summary", ""))[:200]} (output 없음)'
        raw = raw["output"]
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return "failed", [], "items 없음"
    want = sorted((n["id"], n["term"]) for n in names)
    got = sorted((i.get("id"), i.get("term")) for i in items if isinstance(i, dict))
    if got != want:
        return "failed", [], f"id/term 불일치: 요청 {want} 응답 {got}"
    if any(not str(i.get("explanation", "")).strip() for i in items):
        return "failed", [], "빈 설명"
    return "ok", items, ""


def make_backend(kind: str, model: str, art_dir: Path):
    cancel = lambda: False  # noqa: E731
    if kind in ("claude", "qwen"):  # 평문 입출력(plain_runner). 지시문은 부를 때 읽는다(collect_variants가 바꿈)
        import plain_runner

        return plain_runner.make_backend(kind, model, art_dir, lambda: INSTR_NOW())
    if kind == "gpt":
        run_agent = load_adapters().run_agent  # gpt-6-luna(OMP) 격리 실행기, 모델은 실행기 설정

        import plain_runner
        import time

        def call(names, timeout):
            t0 = time.perf_counter()
            try:
                return run_agent({"names": names}, GPT_PERSONA + INSTR_NOW() + GPT_TAIL, timeout, None, cancel, art_dir)
            finally:
                plain_runner.record("gpt", model, time.perf_counter() - t0)  # 토큰은 동봉 실행기가 주지 않음
        return call
    raise SystemExit(f"알 수 없는 백엔드: {kind}")


def INSTR_NOW() -> str:  # noqa: N802 — 모듈 전역 INSTR을 부를 때 읽는다
    return INSTR


def collect(call, rules: dict, rules_file: str, k: int, out: Path, model: str, backend: str,
            timeout: float, mode: str = "solo") -> None:
    targets = [{"id": rid, "term": r["term"], "role": "target"} for rid, r in rules.items()]
    contrasts = [{"id": rid, "term": c, "role": "contrast"} for rid, r in rules.items() for c in r.get("contrasts", [])]
    done = set()
    if out.exists():
        for x in (json.loads(s) for s in out.read_text(encoding="utf-8").splitlines() if s.strip()):
            if x["status"] == "ok":
                done.add((x["role"], tuple(n["term"] for n in x["names"]), x["round"]))
    jobs = []
    for rnd in range(k):
        for role, group in (("target", targets), ("contrast", contrasts)):
            if not group:
                continue
            if mode == "list":
                jobs.append((role, group if rnd % 2 == 0 else group[::-1], rnd))
            else:
                jobs += [(role, [n], rnd) for n in group]
    with out.open("a", encoding="utf-8") as fh:
        for role, group, rnd in jobs:
            names = [{"id": n["id"], "term": n["term"]} for n in group]
            if (role, tuple(n["term"] for n in names), rnd) in done:
                continue
            try:
                status, items, err = validate(call(names, timeout), names)
            except TimeoutError as exc:
                status, items, err = "timed_out", [], repr(exc)
            except Exception as exc:  # noqa: BLE001 — 어떤 실패도 표본으로 남기고 계속
                status, items, err = "failed", [], f"{type(exc).__name__}: {exc}"
            rec = {"format": "samples/v2", "role": role, "round": rnd, "mode": mode, "backend": backend,
                   "model": model, "instr_sha": instr_sha(), "rules_file": rules_file,
                   "rule_hashes": {n["id"]: rule_hash(rules[n["id"]]) for n in names},
                   "names": names, "status": status, "error": err, "items": items}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"{role} r{rnd} {','.join(n['term'] for n in names)[:60]} {status} {err[:80]}", flush=True)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    kind, model, rules_path, k, out = a[0], a[1], Path(a[2]), int(a[3]), Path(a[4])
    timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a else 300.0
    call = make_backend(kind, model, out.parent / f"art_{out.stem}")
    collect(call, load_rules(rules_path), str(rules_path), k, out, model, kind, timeout,
            "list" if "--list" in a else "solo")


if __name__ == "__main__":
    main()
