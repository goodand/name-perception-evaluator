"""이름 충돌 조회: PyPI·npm·GitHub를 free/taken/unverified로 기록 (하네스 v2.2).

사용: python scripts/check_availability.py <이름…> [--rules <규칙.json|yaml>] [--out <out.jsonl>]
- 조회 실패(시간 초과·403·429·5xx·이상한 응답)는 unverified이고 free로 치지 않는다(quaere-naming 가용성 게이트).
- GitHub는 이름 정확 일치(대소문자 무시)만 taken. 결과가 잘려(total_count > items) 일치가 안 보이면 unverified.
- 이 PC에서는 Bash의 네트워크가 막혀 있다: PowerShell에서 .venv Python으로 실행한다.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def pypi_name(name: str) -> str:
    """PEP 503 정규화: 소문자, [-_.] 연속은 '-' 하나."""
    return re.sub(r"[-_.]+", "-", name).lower()


def registry_status(code) -> str:
    return {200: "taken", 404: "free"}.get(code, "unverified")


def github_status(name: str, code, body) -> tuple[str, list[str]]:
    if code != 200 or not isinstance(body, dict) or not isinstance(body.get("items"), list) \
            or body.get("incomplete_results"):
        return "unverified", []
    hits = [i.get("full_name", i.get("name")) for i in body["items"] if str(i.get("name", "")).lower() == name.lower()]
    if hits:
        return "taken", hits
    if body.get("total_count", 0) > len(body["items"]):
        return "unverified", []
    return "free", []


def overall(st: dict) -> str:
    vals = set(st.values())
    return "taken" if "taken" in vals else "unverified" if "unverified" in vals else "free"


def fetch(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers={"User-Agent": "name-harness-availability/1",
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, None


def _safe(call, url):
    try:
        return call(url)
    except Exception:  # noqa: BLE001 — 어떤 실패도 unverified
        return None, None


def check(name: str, fetcher=fetch) -> dict:
    p_code, _ = _safe(fetcher, f"https://pypi.org/pypi/{pypi_name(name)}/json")
    n_code, _ = _safe(fetcher, f"https://registry.npmjs.org/{name.lower()}")
    g_code, g_body = _safe(fetcher, f"https://api.github.com/search/repositories?q={name}+in:name&per_page=100")
    gh, hits = github_status(name, g_code, g_body)
    st = {"pypi": registry_status(p_code), "npm": registry_status(n_code), "github": gh}
    return {"name": name, **st, "github_exact": hits, "overall": overall(st)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    names = []
    if "--rules" in a:
        sys.path.insert(0, str(Path(__file__).parent))
        from check_terms import load_rules

        names += [r["term"] for r in load_rules(Path(a[a.index("--rules") + 1])).values()]
    skip = {a.index(f) + 1 for f in ("--rules", "--out") if f in a}
    names += [x for i, x in enumerate(a) if not x.startswith("--") and i not in skip]
    out = Path(a[a.index("--out") + 1]) if "--out" in a else None
    fh = out.open("a", encoding="utf-8") if out else None
    for n in names:
        r = check(n)
        print(f'{n} | {r["overall"]} | pypi={r["pypi"]} npm={r["npm"]} github={r["github"]}'
              + (f' {r["github_exact"]}' if r["github_exact"] else ""), flush=True)
        if fh:
            fh.write(json.dumps({**r, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")
        time.sleep(2)  # GitHub 비인증 검색 한도(분당 10회) 회피
    if fh:
        fh.close()


if __name__ == "__main__":
    main()
