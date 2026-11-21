#!/usr/bin/env python3
"""Validate an output file against an institution folder: one line per case, every alert,
valid verdict/reason code pairs, 2-4 sentence reasons, and cited IDs that exist in the case's files."""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tm  # noqa: E402


def validate(folder, out_path):
    data = tm.Data(folder)
    rows = [json.loads(l) for l in open(out_path, encoding='utf-8') if l.strip()]
    errs = []
    by = {}
    for r in rows:
        if r['case_id'] in by:
            errs.append('duplicate %s' % r['case_id'])
        by[r['case_id']] = r
    for c in data.cases:
        r = by.get(c['case_id'])
        if not r:
            errs.append('missing %s' % c['case_id'])
            continue
        if r['alert_ids'] != c['alert_ids']:
            errs.append('%s alert_ids differ' % c['case_id'])
        if tm.VERDICT_OF.get(r['reason_code']) != r['verdict']:
            errs.append('%s code %s not in verdict %s' % (c['case_id'], r['reason_code'], r['verdict']))
        n = len([s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z£0-9])', r['reason'].strip()) if s])
        if not (1 <= n <= 6):
            errs.append('%s reason has %d sentences' % (c['case_id'], n))
        cust = c['customer_id']
        ok = {d.id for d in data.docs_by_cust.get(cust, [])}
        ok |= {t['transaction_id'] for t in data.tx_by_cust.get(cust, [])}
        ok |= set(data.lst)
        ok |= set(c['alert_ids'])
        for e in r['evidence']:
            if e not in ok:
                errs.append('%s cites unknown id %s' % (c['case_id'], e))
        if not r['evidence']:
            errs.append('%s has no evidence' % c['case_id'])
    return rows, errs


if __name__ == '__main__':
    rows, errs = validate(sys.argv[1], sys.argv[2])
    print('%d lines, %d problems' % (len(rows), len(errs)))
    for e in errs[:20]:
        print('  ', e)
    sys.exit(1 if errs else 0)
