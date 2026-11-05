"""check_availability.py 명세: 레지스트리 응답 → free/taken/unverified (네트워크 없이 판정 함수만).

규칙(quaere-naming 가용성 게이트를 따름): 조회 실패는 unverified이고 free로 치지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_availability as ca  # noqa: E402


def test_registry_status():
    assert ca.registry_status(200) == "taken"
    assert ca.registry_status(404) == "free"
    for code in (403, 429, 500, None):
        assert ca.registry_status(code) == "unverified"


def test_github_status():
    items = [{"name": "Foo-Bar", "full_name": "x/Foo-Bar", "stargazers_count": 3}, {"name": "foo-barz"}]
    st, hits = ca.github_status("foo-bar", 200, {"total_count": 2, "items": items})
    assert st == "taken" and hits == ["x/Foo-Bar"]  # 대소문자 무시, 정확히 같은 이름만
    assert ca.github_status("foo-bar", 200, {"total_count": 1, "items": [{"name": "foo-barz"}]})[0] == "free"
    assert ca.github_status("foo-bar", 403, None)[0] == "unverified"
    assert ca.github_status("foo-bar", 200, {"incomplete_results": True, "items": []})[0] == "unverified"


def test_overall():
    assert ca.overall({"pypi": "free", "npm": "free", "github": "free"}) == "free"
    assert ca.overall({"pypi": "free", "npm": "taken", "github": "unverified"}) == "taken"
    assert ca.overall({"pypi": "free", "npm": "free", "github": "unverified"}) == "unverified"


def test_github_truncated_or_malformed_is_unverified():
    """정확히 같은 이름이 잘린 결과 밖에 있을 수 있으면 free로 치지 않는다."""
    many = {"total_count": 45, "items": [{"name": f"x{i}"} for i in range(30)]}
    assert ca.github_status("foo", 200, many)[0] == "unverified"
    assert ca.github_status("foo", 200, None)[0] == "unverified"
    assert ca.github_status("foo", 200, {"total_count": 0})[0] == "unverified"


def test_pypi_name_normalized():
    assert ca.pypi_name("Foo_Bar.baz") == "foo-bar-baz"


def test_exact_urls():
    seen = []

    def fetch(url):
        seen.append(url)
        return 404, None
    ca.check("Foo_Bar", fetch)
    assert seen == ["https://pypi.org/pypi/foo-bar/json", "https://registry.npmjs.org/foo_bar",
                    "https://api.github.com/search/repositories?q=Foo_Bar+in:name&per_page=100"]


def test_check_uses_fetcher():
    """네트워크 호출은 주입한 fetch로만. 예외는 unverified."""
    def fetch(url):
        if "pypi" in url:
            return 404, None
        if "npmjs" in url:
            raise TimeoutError
        return 200, {"total_count": 0, "items": []}
    r = ca.check("some-name", fetch)
    assert r == {"name": "some-name", "pypi": "free", "npm": "unverified", "github": "free",
                 "github_exact": [], "overall": "unverified"}
