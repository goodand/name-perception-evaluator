"""답변자 재실험: 지시문(상황 설명)만 바꿔 같은 이름을 다시 수집한다 (하네스 v2.2).

사용: python scripts/collect_variants.py <qwen|gpt|claude> <model_id> <rules> <k> <out_dir> --variants <variants.json>
      [--list] [--timeout 초]
variants.json: {"V1": "상황 설명 문장", ...}. 출력 형식 부분은 collect_samples.INSTR에서 그대로 가져와 고정한다.
collect_samples.py는 고치지 않는다: 모듈의 INSTR을 잠시 바꿔 collect()를 부르고 끝나면 되돌린다.
표본의 instr_sha가 지시문마다 달라지므로 `check_terms.py --by instr_sha`로 지시문별 판정을 비교한다.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import collect_samples as cs  # noqa: E402
from check_terms import load_rules  # noqa: E402

CONTRACT = cs.CONTRACT  # 원본 지시문의 답변 요구 부분 그대로(관점 문장만 바꾼다)


def compose(framing: str) -> str:
    return f"{framing.strip()} {CONTRACT}"


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def collect_variant(call, vid: str, framing: str, rules: dict, rules_file: str, k: int, out_dir: Path, model: str,
                    backend: str, timeout: float, mode: str = "solo") -> Path:
    out = Path(out_dir) / f"{Path(rules_file).stem}_{backend}_{vid}.jsonl"
    before = cs.INSTR
    cs.INSTR = compose(framing)
    try:
        cs.collect(call, rules, rules_file, k, out, model, backend, timeout, mode)
    finally:
        cs.INSTR = before
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    kind, model, rules_path, k, out_dir = a[0], a[1], Path(a[2]), int(a[3]), Path(a[4])
    variants = json.loads(Path(a[a.index("--variants") + 1]).read_text(encoding="utf-8"))
    timeout = float(a[a.index("--timeout") + 1]) if "--timeout" in a else 300.0
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = load_rules(rules_path)
    for vid, framing in variants.items():
        call = cs.make_backend(kind, model, out_dir / f"art_{kind}_{vid}")
        out = collect_variant(call, vid, framing, rules, str(rules_path), k, out_dir, model, kind, timeout,
                              "list" if "--list" in a else "solo")
        print(f"{vid} → {out} (instr_sha {sha(compose(framing))})", flush=True)


if __name__ == "__main__":
    main()
