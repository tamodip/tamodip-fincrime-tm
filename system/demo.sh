#!/bin/sh
# Demo run: system/demo.sh <institution folder | institutions root> [out dir]
# Runs the system on each institution (timed, with the engine trace), validates the output,
# builds the offline viewer (out dir/index.html) and opens it.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:?usage: system/demo.sh <institution folder | institutions root> [out dir]}"
OUT="${2:-$HERE/../demo_out}"
mkdir -p "$OUT"
printf '\n  Alert Closer - deterministic transaction-monitoring triage\n  no model . stdlib only . $0\n\n'
if [ -f "$SRC/cases.jsonl" ]; then FOLDERS="$SRC"; else FOLDERS=$(for d in "$SRC"/*/; do [ -f "$d/cases.jsonl" ] && echo "${d%/}"; done); fi
ARGS=""; RTS=""
for F in $FOLDERS; do
  N=$(basename "$F")
  T0=$(python3 -c 'import time;print(time.time())')
  TM_TRACE="$OUT/$N.trace.json" "$HERE/run" "$F" "$OUT/$N.jsonl"
  T1=$(python3 -c 'import time;print(time.time())')
  RT=$(python3 -c "print('%.2f' % ($T1 - $T0))")
  python3 "$HERE/tests/validate.py" "$F" "$OUT/$N.jsonl" | sed "s/^/  $N: /"
  python3 -c "import json,collections,sys;c=collections.Counter(json.loads(l)['verdict'] for l in open(sys.argv[1]));print('  %s: %s in %ss' % (sys.argv[2], dict(c), sys.argv[3]))" "$OUT/$N.jsonl" "$N" "$RT"
  ARGS="$ARGS $F $OUT/$N.jsonl $OUT/$N.trace.json"; RTS="$RTS --runtime $N=$RT"
done
python3 "$HERE/viewer/build_viewer.py" "$OUT/index.html" $ARGS $RTS | sed 's/^/  /'
echo "  open: $OUT/index.html   (deep link: index.html#<CASE_ID>)"
if [ -n "$NO_OPEN" ]; then :
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$OUT/index.html" >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then open "$OUT/index.html" || true; fi
