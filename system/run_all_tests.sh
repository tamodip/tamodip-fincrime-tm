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
    mkdir -p "$TMP/sub"; cp -r "$d"/. "$TMP/sub/"
    python3 -c "import random,sys;p=sys.argv[1];l=open(p).readlines();random.Random(7).shuffle(l);open(p,'w').writelines(l[:200])" "$TMP/sub/cases.jsonl"
    "$HERE/run" "$TMP/sub" "$TMP/sub.jsonl"
    python3 -c "import json,sys;f={json.loads(l)['case_id']:json.loads(l) for l in open(sys.argv[1])};d=[r['case_id'] for r in map(json.loads,open(sys.argv[2])) if r!=f[r['case_id']]];print('== 200-case subset $N: %d differences from the full run' % len(d));sys.exit(1 if d else 0)" "$TMP/$N.a.jsonl" "$TMP/sub.jsonl"
    rm -rf "$TMP/sub"
    if [ -z "$QUICK" ]; then echo "== stress $N"; python3 "$HERE/tests/stress.py" "$d"; fi
  done
  rm -rf "$TMP"
fi
echo "ALL TESTS PASSED"
