#!/usr/bin/env bash
# 판정·선택·수정 프로토콜 모델 증명 + 차분 테스트. scripts/check_terms.py·prompt_check.py 또는 formal/ 이 바뀌면 돈다(.claude/settings.json 훅).
#   1) lake build  — tests 명세 정리 39개가 sorry 없이 증명되는지 (Lean 4.33, 로컬 Docker 이미지)
#   2) lean --run Diff.lean → diff_test.py — 모델과 파이썬이 같은 입력 500건에 같은 답을 내는지
# 종료 코드 0 = 둘 다 통과. 그 외 = 깨짐(훅이 그 세션에 그대로 보여 준다). 파일은 고치지 않는다.
set -uo pipefail
export PYTHONIOENCODING=utf-8
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
LEAN_DIR="$ROOT/formal/name-harness/lean"
IMAGE="${NAME_HARNESS_LEAN_IMAGE:-lean4:4.33.0-20261103-v1}"
if [ -x "$ROOT/.venv/Scripts/python.exe" ]; then PY="$ROOT/.venv/Scripts/python.exe"; else PY="$ROOT/.venv/bin/python"; fi
[ -x "$PY" ] || PY=python

if ! command -v docker >/dev/null 2>&1 || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "[verify] Lean 증명 건너뜀: docker 또는 이미지 $IMAGE 없음 (차분 테스트도 Lean 출력이 필요해 건너뜀)"
  exit 0
fi
WIN_DIR="$(cd "$LEAN_DIR" && pwd -W 2>/dev/null || pwd)"
out="$(MSYS_NO_PATHCONV=1 docker run --rm -v "$WIN_DIR:/w" -w /w "$IMAGE" \
  sh -c 'lake build 2>&1 && lake env lean --run Diff.lean > /w/diff_out.txt 2>&1 && lake env lean --run LemmaDiff.lean > /w/lemma_out.txt 2>&1' 2>&1)"
rc=$?
if [ $rc -ne 0 ] || ! grep -q "Build completed successfully" <<<"$out"; then
  echo "[verify] Lean 증명 실패 — 테스트 명세 정리가 더는 성립하지 않거나 모델이 코드와 어긋났다:"
  grep -E "^error|sorry" <<<"$out" | head -20
  exit 2
fi
res="$("$PY" "$ROOT/formal/name-harness/diff_test.py" "$LEAN_DIR/diff_out.txt" 2>&1)"
rc=$?
echo "$res" | tail -3
if [ $rc -ne 0 ]; then
  echo "[verify] 차분 테스트 불일치 — 파이썬 판정과 Lean 모델이 다른 답을 냈다. 코드를 바꿨으면 모델(formal/name-harness/lean/NameHarness/System.lean)과 정리도 같이 고쳐야 한다."
  exit 2
fi
res="$("$PY" "$ROOT/formal/name-harness/lemma_diff.py" "$LEAN_DIR/lemma_out.txt" 2>&1)"
rc=$?
echo "$res" | tail -2
if [ $rc -ne 0 ]; then
  echo "[verify] 두 단계 금지어 검사(prompt_check.check)와 Lean 모델(Lemma.lean)이 어긋났다."
  exit 2
fi
echo "[verify] 정리 통과(sorry 0), 차분 테스트 500건·두 단계 검사 1200건 일치"
