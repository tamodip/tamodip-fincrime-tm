#!/bin/sh
# Runs every test: policy unit tests, 30 synthetic edge cases, output validation, determinism (run twice + diff)
# and, with an institutions root, the paraphrase/format stress harness.
#   system/run_all_tests.sh [institutions root]
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="${1:-$HERE/../institutions}"
echo "== policy unit tests"; python3 "$HERE/tests/test_policy.py"
echo "== edge cases"; python3 "$HERE/tests/edge_cases.py"
if [ -d "$ROOT" ]; then
  TMP=$(mktemp -d)
  for d in "$ROOT"/*/; do
    [ -f "$d/cases.jsonl" ] || continue
    N=$(basename "$d")
    "$HERE/run" "$d" "$TMP/$N.a.jsonl"; "$HERE/run" "$d" "$TMP/$N.b.jsonl"
    python3 "$HERE/tests/validate.py" "$d" "$TMP/$N.a.jsonl" | sed "s/^/== validate $N: /"
    if cmp -s "$TMP/$N.a.jsonl" "$TMP/$N.b.jsonl"; then echo "== determinism $N: identical ($(sha256sum < "$TMP/$N.a.jsonl" | cut -c1-16))"; else echo "== determinism $N: DIFFERENT"; exit 1; fi
    if [ -z "$QUICK" ]; then echo "== stress $N"; python3 "$HERE/tests/stress.py" "$d"; fi
  done
  rm -rf "$TMP"
fi
echo "ALL TESTS PASSED"
