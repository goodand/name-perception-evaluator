#!/usr/bin/env bash
# PostToolUse 훅 진입점: 바뀐 파일이 판정·선택 코드나 formal/ 이면 verify.sh 를 돈다. 그 외 파일은 바로 통과.
# stdin: Claude Code 훅 JSON ({"tool_input":{"file_path":...}, ...}). 종료 코드 2 = 세션에 메시지로 전달.
set -uo pipefail
export PYTHONIOENCODING=utf-8
HERE="$(cd "$(dirname "$0")" && pwd)"
input="$(cat)"
path="$(printf '%s' "$input" | "${PYTHON:-python}" -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))' 2>/dev/null)"
path="${path//\\//}"
case "$path" in
  */scripts/check_terms.py|*/scripts/prompt_check.py|*/scripts/search_words.py|*/scripts/prompt_slots.py|*/scripts/name_keywords.py|*/formal/name-harness/*) ;;
  *) exit 0 ;;
esac
out="$(bash "$HERE/verify.sh" 2>&1)"; rc=$?
if [ $rc -ne 0 ]; then
  printf '%s\n' "$out" >&2
  exit 2
fi
printf '%s\n' "$out"
