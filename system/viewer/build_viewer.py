#!/usr/bin/env python3
"""Offline demo viewer: one self-contained HTML page (inline CSS/JS, no network).

    python3 system/viewer/build_viewer.py <out.html> <inst_folder> <output.jsonl> <trace.json> [<inst_folder> <output.jsonl> <trace.json> ...]
        [--runtime name=seconds ...]

It embeds the case files the page needs (alerts, flagged transactions, cited documents), so the
generated HTML contains development data: it is git-ignored.
"""
import json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tm  # noqa: E402

NAMES = {'bank': 'Bank', 'emoney': 'E-money firm', 'investment': 'Investment firm', 'payments_fx': 'Payments & FX firm'}


def build_inst(folder, out_path, trace_path, runtime):
    data = tm.Data(folder)
    rows = [json.loads(l) for l in open(out_path, encoding='utf-8') if l.strip()]
    trace = json.load(open(trace_path, encoding='utf-8')) if trace_path and os.path.exists(trace_path) else {}
    cases = {c['case_id']: c for c in data.cases}
    out = []
    for r in rows:
        c = cases.get(r['case_id'], {})
        cust = data.customers.get(c.get('customer_id'), {})
        tr = trace.get(r['case_id'], {})
        alerts = [data.alerts[a] for a in c.get('alert_ids', []) if a in data.alerts]
        tids = []
        for a in alerts:
            for t in a.get('transaction_ids') or []:
                if t not in tids:
                    tids.append(t)
        checks = {k.get('tx'): k for k in tr.get('checks', []) if k.get('tx')}
        txs = []
        for t in sorted((data.tx[x] for x in tids if x in data.tx), key=lambda t: t.get('booked_at') or ''):
            k = checks.get(t['transaction_id'], {})
            txs.append({'id': t['transaction_id'], 'd': (t.get('booked_at') or '')[:10], 'dir': t['direction'], 'ch': t.get('channel'),
                        'amt': t['amount_gbp'], 'cp': t.get('counterparty_name'), 'ctry': t.get('counterparty_country'),
                        'ref': t.get('reference'), 'res': k.get('result', ''), 'note': k.get('note', ''),
                        'held': t['transaction_id'] == c.get('held_payment_id')})
        docs = {}
        cited = set(r.get('evidence') or [])
        for k in tr.get('checks', []):
            cited |= set(k.get('evidence') or [])
        for f in tr.get('flags', []):
            cited.add(f.get('doc'))
        for d in data.docs_by_cust.get(c.get('customer_id'), []):
            docs[d.id] = {'id': d.id, 'type': d.type, 'dated': d.dated.isoformat() if d.dated else '', 'title': d.title,
                          'text': d.text, 'cited': d.id in cited}
        lst = {}
        for e in cited:
            if e in data.lst:
                lst[e] = data.lst[e]
        out.append({
            'id': r['case_id'], 'v': r['verdict'], 'code': r['reason_code'], 'reason': r['reason'], 'ev': r.get('evidence') or [],
            'rules': sorted(set(a['rule_id'] for a in alerts)),
            'alerts': [{'id': a['alert_id'], 'rule': a['rule_id'], 'name': a.get('rule_name'), 'msg': a.get('message')} for a in alerts],
            'cust': {'id': cust.get('customer_id'), 'name': cust.get('name'), 'kind': cust.get('kind'),
                     'occ': cust.get('occupation') or cust.get('business_activity'), 'risk': cust.get('risk_rating'),
                     'declared': cust.get('declared') or {}},
            'window': c.get('review_window'), 'held': c.get('held_payment_id'),
            'txs': txs, 'flags': tr.get('flags', []), 'checks': [k for k in tr.get('checks', []) if not k.get('tx')],
            'docs': sorted(docs.values(), key=lambda d: (not d['cited'], d['id'])),
            'prev': data.prev.get(c.get('customer_id'), []), 'list': lst,
        })
    name = os.path.basename(os.path.normpath(folder))
    return {'key': name, 'name': NAMES.get(name, name), 'n': len(out), 'runtime': runtime.get(name),
            'mix': dict(Counter(x['v'] for x in out)), 'codes': dict(Counter(x['code'] for x in out)),
            'rules': dict(Counter(r for x in out for r in x['rules'])), 'cases': out}


def main(argv):
    runtime = {}
    args = []
    i = 0
    while i < len(argv):
        if argv[i] == '--runtime':
            k, v = argv[i + 1].split('=')
            runtime[k] = float(v)
            i += 2
        else:
            args.append(argv[i])
            i += 1
    out_html = args[0]
    insts = []
    for j in range(1, len(args), 3):
        insts.append(build_inst(args[j], args[j + 1], args[j + 2], runtime))
    tpl = open(os.path.join(HERE, 'template.html'), encoding='utf-8').read()
    payload = json.dumps({'insts': insts}, ensure_ascii=False, sort_keys=True).replace('</', '<\\/')
    os.makedirs(os.path.dirname(os.path.abspath(out_html)), exist_ok=True)
    open(out_html, 'w', encoding='utf-8').write(tpl.replace('/*__DATA__*/null', payload))
    print('viewer: %s (%d cases, %.1f MB)' % (out_html, sum(x['n'] for x in insts), os.path.getsize(out_html) / 1e6))


if __name__ == '__main__':
    main(sys.argv[1:])
