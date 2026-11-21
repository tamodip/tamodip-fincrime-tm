#!/usr/bin/env python3
"""EDGE_CASES: synthetic, deliberately awkward cases built from scratch (no development data).

Each case is a tiny world: one customer, its transactions, documents and alerts. We write them into
a temporary institution folder, run the real system on it and check the verdict (and, where it
matters, the reason code). Run: python3 system/tests/edge_cases.py
"""
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.dirname(HERE)
POLICY = open(os.path.join(HERE, 'fixtures', 'POLICY_bank.md'), encoding='utf-8').read()
POLICY_PX = open(os.path.join(HERE, 'fixtures', 'POLICY_payments_fx.md'), encoding='utf-8').read()

CASES = []


def case(name, expect, code=None, policy='bank'):
    def deco(fn):
        CASES.append((name, expect, code, policy, fn))
        return fn
    return deco


class World:
    def __init__(self, n, kind='individual', income=2500, turnover=None, countries=('United Kingdom',),
                 name='Alex Example', employer='Example Employer Ltd', activity=None):
        self.n = n
        self.cid = 'XX-C%04d' % n
        self.name = name
        self.customer = {'customer_id': self.cid, 'kind': kind, 'name': name, 'date_of_birth': '1985-01-01',
                         'occupation': 'Engineer', 'employer': employer, 'business_activity': activity,
                         'account_ids': ['XX-A%04d' % n],
                         'declared': {'monthly_income_gbp': income, 'annual_turnover_gbp': turnover,
                                      'expected_countries': list(countries), 'source_of_funds': 'Salary'}}
        self.tx, self.docs, self.alerts, self.lst, self.prev = [], [], [], [], []
        self.held = None
        self.k = 0

    def t(self, date, direction, amount, cp, channel='faster_payment', ref='', country='United Kingdom', account=None):
        self.k += 1
        tid = 'XX-T%04d%03d' % (self.n, self.k)
        self.tx.append({'transaction_id': tid, 'customer_id': self.cid, 'account_id': 'XX-A%04d' % self.n,
                        'booked_at': date + 'T10:00:00Z', 'direction': direction, 'channel': channel,
                        'amount_gbp': amount, 'amount': amount, 'currency': 'GBP', 'counterparty_name': cp,
                        'counterparty_account': account, 'counterparty_country': country, 'reference': ref})
        return tid

    def doc(self, typ, dated, body, prefix='DOC'):
        self.k += 1
        did = '%s-%d%03d' % (prefix, self.n, self.k)
        self.docs.append(({'doc_id': did, 'customer_id': self.cid, 'type': typ, 'title': typ.replace('_', ' '),
                           'dated': dated, 'file': 'evidence/%s.md' % did},
                          '# %s\n\n**Document ID:** %s\n**Dated:** %s\n\n%s\n' % (typ, did, dated, body)))
        return did

    def alert(self, rule, tids, measured=None, message=''):
        self.k += 1
        aid = 'XX-AL%04d%03d' % (self.n, self.k)
        self.alerts.append({'alert_id': aid, 'case_id': 'XX-CS%04d' % self.n, 'customer_id': self.cid, 'rule_id': rule,
                            'rule_name': rule, 'message': message or rule, 'measured': measured or {}, 'transaction_ids': tids})
        return aid

    def listed(self, eid, name, dob, address=None, reason='Subject of an internal investigation.'):
        self.lst.append({'entry_id': eid, 'kind': 'individual', 'name': name, 'date_of_birth': dob, 'identifiers': {},
                         'address': address, 'reason': reason})


def build(folder, worlds, policy_text):
    os.makedirs(os.path.join(folder, 'evidence'))
    open(os.path.join(folder, 'POLICY.md'), 'w').write(policy_text)
    files = {k: [] for k in ('cases', 'alerts', 'customers', 'transactions', 'evidence', 'previous_reviews', 'internal_list')}
    for w in worlds:
        files['cases'].append({'case_id': 'XX-CS%04d' % w.n, 'customer_id': w.cid, 'review_window': {'from': '2026-08-01', 'to': '2026-08-31'},
                               'alert_ids': [a['alert_id'] for a in w.alerts], 'held_payment_id': w.held})
        files['alerts'] += w.alerts
        files['customers'].append(w.customer)
        files['transactions'] += w.tx
        files['previous_reviews'] += w.prev
        files['internal_list'] += w.lst
        for meta, text in w.docs:
            files['evidence'].append(meta)
            open(os.path.join(folder, meta['file']), 'w').write(text)
    for k, rows in files.items():
        with open(os.path.join(folder, k + '.jsonl'), 'w') as f:
            for r in rows:
                f.write(json.dumps(r) + '\n')


# ------------------------------------------------------------------ the cases
@case('invoice matches amount, payee and date', 'CLOSE', 'INVOICE_MATCHES')
def _(w):
    t = w.t('2026-08-10', 'out', 4200.00, 'Oakfield Kitchens Ltd', ref='INV 5521')
    w.doc('invoice', '2026-08-01', '**Bill to:** %s\n**Description:** fitted kitchen\n**Amount due:** £4,200.00\n**Pay to:** Oakfield Kitchens Ltd' % w.name, 'INV')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('invoice off by £35 does not explain the payment', 'RFI')
def _(w):
    t = w.t('2026-08-10', 'out', 4235.00, 'Oakfield Kitchens Ltd', ref='INV 5521')
    w.doc('invoice', '2026-08-01', '**Amount due:** £4,200.00\n**Pay to:** Oakfield Kitchens Ltd', 'INV')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('invoice dated after the payment is a mismatch', 'ESCALATE', 'ESC_INVOICE_MISMATCH')
def _(w):
    t = w.t('2026-08-10', 'out', 4200.00, 'Oakfield Kitchens Ltd', ref='INV 5521')
    w.doc('invoice', '2026-08-20', '**Amount due:** £4,200.00\n**Pay to:** Oakfield Kitchens Ltd', 'INV')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('invoice names a different payee', 'ESCALATE', 'ESC_INVOICE_MISMATCH')
def _(w):
    t = w.t('2026-08-10', 'out', 4200.00, 'Quickcash Trading Ltd')
    w.doc('invoice', '2026-08-01', '**Amount due:** £4,200.00\n**Pay to:** Oakfield Kitchens Ltd', 'INV')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('one of two alerts explained, the other not', 'RFI')
def _(w):
    a = w.t('2026-08-10', 'in', 12000.00, 'Dunmore Motors Ltd', ref='CAR SALE')
    b = w.t('2026-08-12', 'in', 9000.00, 'Robin Stranger', ref='payment')
    w.doc('vehicle_sale_receipt', '2026-08-09', 'Received from Dunmore Motors Ltd the sum of £12,000.00 for a 2019 hatchback. **Seller:** %s' % w.name, 'SAL')
    w.alert('TM01', [a, b], {'multiple': 8.4})


@case('own account proven by statement in customer name', 'CLOSE', 'OWN_ACCOUNT')
def _(w):
    t = w.t('2026-08-10', 'in', 6000.00, w.name, ref='OWN TRANSFER', account='11-22-33 44556677')
    w.doc('bank_statement', '2026-08-11', '**Account holder:** %s\n**Bank:** Northgate Bank\n**Account:** 11-22-33 44556677\n\n10 August 2026: transfer of £6,000.00 out.' % w.name, 'STM')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('own account claimed but statement is in someone else\'s name', 'ESCALATE', 'ESC_ACCOUNT_MISUSE')
def _(w):
    t = w.t('2026-08-10', 'in', 6000.00, w.name, ref='OWN TRANSFER', account='11-22-33 44556677')
    w.doc('bank_statement', '2026-08-11', '**Account holder:** Jamie Other\n**Bank:** Northgate Bank\n**Account:** 11-22-33 44556677\n\n10 August 2026: transfer of £6,000.00 out.', 'STM')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('own account without any document', 'RFI')
def _(w):
    t = w.t('2026-08-10', 'in', 6000.00, w.name, ref='OWN TRANSFER', account='11-22-33 44556677')
    w.alert('TM01', [t], {'multiple': 3.4})


@case('own-account transfers at 5x declared income need an updated profile', 'RFI', 'RFI_UPDATED_PROFILE')
def _(w):
    t = w.t('2026-08-10', 'in', 14000.00, w.name, ref='OWN TRANSFER', account='11-22-33 44556677')
    w.doc('bank_statement', '2026-08-11', '**Account holder:** %s\n**Bank:** Northgate Bank\n**Account:** 11-22-33 44556677\n\n10 August 2026: transfer of £14,000.00 out.' % w.name, 'STM')
    w.alert('TM01', [t], {'multiple': 5.6})


@case('list hit: same name, different date of birth', 'CLOSE', 'LIST_MATCH_DIFFERENT_PARTY')
def _(w):
    t = w.t('2026-08-10', 'in', 15000.00, 'Morgan Listed', ref='GIFT')
    w.listed('XX-L1', 'Morgan Listed', '1960-03-04')
    w.doc('gift_letter', '2026-08-09', 'I, Morgan Listed, born 12 July 1971, give £15,000.00 to my relative %s as a gift.' % w.name, 'GFT')
    w.alert('TM22', [t], {'list_entry': 'XX-L1', 'matched_on': 'name'})
    w.alert('TM08', [t])


@case('list hit: same name and same date of birth (DOB: wording)', 'ESCALATE', 'ESC_LISTED_PARTY')
def _(w):
    t = w.t('2026-08-10', 'in', 15000.00, 'Morgan Listed', ref='GIFT')
    w.listed('XX-L1', 'Morgan Listed', '1960-03-04')
    w.doc('gift_letter', '2026-08-09', 'I, Morgan Listed (DOB: 4 March 1960), give £15,000.00 to my relative %s as a gift.' % w.name, 'GFT')
    w.alert('TM22', [t], {'list_entry': 'XX-L1', 'matched_on': 'name'})


@case('list hit: name only, nothing on file', 'RFI', 'RFI_COUNTERPARTY_DETAILS')
def _(w):
    t = w.t('2026-08-10', 'out', 900.00, 'Morgan Listed', ref='garden work')
    w.listed('XX-L1', 'Morgan Listed', '1960-03-04')
    w.alert('TM22', [t], {'list_entry': 'XX-L1', 'matched_on': 'name'})


@case('listed director resigned before the payment', 'CLOSE', 'LIST_MATCH_DIFFERENT_PARTY')
def _(w):
    t = w.t('2026-08-15', 'out', 1800.00, 'Elmcote Training Ltd', ref='EL/1')
    w.listed('XX-L2', 'Emery Listed', '1978-08-14')
    w.doc('invoice', '2026-08-10', '**Amount due:** £1,800.00\n**Pay to:** Elmcote Training Ltd', 'INV')
    w.doc('company_register_extract', '2026-08-18', '**Company:** Elmcote Training Ltd\n\n| Officer | Role | Born | Appointed | Resigned |\n|---|---|---|---|---|\n| Emery Listed | Director | August 1978 | 4 March 2023 | 1 June 2026 |\n| Kai New | Director | July 1998 | 26 May 2026 | |', 'REG')
    w.alert('TM22', [t], {'list_entry': 'XX-L2', 'matched_on': 'company officer name and month and year of birth'})


@case('listed person still a controller on the payment date', 'ESCALATE', 'ESC_LISTED_PARTY')
def _(w):
    t = w.t('2026-08-15', 'out', 1800.00, 'Elmcote Training Ltd', ref='EL/1')
    w.listed('XX-L2', 'Emery Listed', '1978-08-14')
    w.doc('invoice', '2026-08-10', '**Amount due:** £1,800.00\n**Pay to:** Elmcote Training Ltd', 'INV')
    w.doc('significant_control_register', '2026-08-18', '| Person | Born | Control | Notified | Ceased |\n|---|---|---|---|---|\n| Emery Listed | August 1978 | 60% | 17 May 2022 | 17 August 2026 |', 'PSC')
    w.alert('TM22', [t], {'list_entry': 'XX-L2', 'matched_on': 'company officer name and month and year of birth'})


@case('structuring question in a staff note overrides matching invoice', 'ESCALATE', 'ESC_STRUCTURING')
def _(w):
    ts = [w.t('2026-08-0%d' % d, 'out', 9500.00 + d, 'Kingston Trading FZE', ref='INV 1', country='United Arab Emirates') for d in (2, 4, 6)]
    w.doc('invoice', '2026-08-01', '**Total:** £%s\n**Terms:** instalments' % '{:,.2f}'.format(sum(9500.00 + d for d in (2, 4, 6))), 'INV')
    w.doc('staff_note', '2026-08-02', 'The director wondered if paying in instalments of less than £10,000 would mean no invoices are needed.', 'NTE')
    w.alert('TM03', ts)


@case('fraud report from the sending bank', 'ESCALATE', 'ESC_MULE_ACTIVITY')
def _(w):
    ts = [w.t('2026-08-0%d' % d, 'in', 400.0 + d, 'Payer %d' % d, ref='for the phone') for d in range(1, 8)]
    o = w.t('2026-08-08', 'out', 2800.00, 'Coinvale Exchange Ltd')
    w.doc('sending_bank_fraud_report', '2026-08-09', 'Our customer Payer 3 sent £403.00 to your customer and reports an authorised push payment scam.', 'FRD')
    w.alert('TM04', ts)
    w.alert('TM02', ts + [o])


@case('refund larger than the original payment is not a refund', 'RFI')
def _(w):
    w.t('2026-06-15', 'out', 5000.00, 'Kelstead Hotel', ref='BOOKING 59396', country='Lebanon')
    t = w.t('2026-08-13', 'in', 7702.22, 'Kelstead Hotel', ref='REFUND BOOKING 59396', country='Lebanon')
    w.doc('venue_email', '2026-08-11', 'We have processed a full refund of your deposit of £5,000.00 for BOOKING 59396.', 'EML')
    w.alert('TM01', [t], {'multiple': 3.6})


@case('dormant account: re-verified on a new device is misuse', 'ESCALATE', 'ESC_ACCOUNT_MISUSE')
def _(w):
    t = w.t('2026-08-10', 'in', 9000.00, w.name, ref='SAVINGS', account='11-22-33 44556677')
    w.doc('bank_statement', '2026-08-11', '**Account holder:** %s\n**Bank:** Northgate Bank\n**Account:** 11-22-33 44556677\n\n10 August 2026: transfer of £9,000.00 out.' % w.name, 'STM')
    w.doc('reverification_record', '2026-08-09', 'Customer re-verified on 9 August 2026 with a live selfie on a new device not previously registered.', 'RVF')
    w.alert('TM07', [t])


@case('dormant account: verified returning customer moving own savings', 'CLOSE', 'RETURNING_CUSTOMER')
def _(w):
    t = w.t('2026-08-10', 'in', 9000.00, w.name, ref='SAVINGS', account='11-22-33 44556677')
    w.doc('bank_statement', '2026-08-11', '**Account holder:** %s\n**Bank:** Northgate Bank\n**Account:** 11-22-33 44556677\n\n10 August 2026: transfer of £9,000.00 out.' % w.name, 'STM')
    w.doc('reverification_record', '2026-08-09', 'Customer re-verified on 9 August 2026 with a live selfie on the device already registered. Address confirmed.', 'RVF')
    w.alert('TM07', [t])


@case('high-risk corridor fan-out of identical amounts', 'ESCALATE', 'ESC_HIGH_RISK_CORRIDOR')
def _(w):
    ins = [w.t('2026-08-1%d' % d, 'in', 7000.0 + d * 13, 'Sender %d' % d) for d in range(3)]
    outs = [w.t('2026-08-1%d' % (d + 3), 'out', 4803.01, 'Receiver %d' % d, channel='swift', country='Lebanon') for d in range(4)]
    w.doc('support_chat', '2026-08-18', '**Customer:** I am sending money to help my family there.', 'CHT')
    w.alert('TM01', ins, {'multiple': 8.4})
    w.alert('TM06', outs)


@case('high-risk corridor with a matching hospital invoice', 'CLOSE', 'INVOICE_MATCHES')
def _(w):
    t = w.t('2026-08-10', 'out', 9680.13, 'Selden Medical Center', channel='swift', country='Lebanon', ref='PATIENT')
    w.doc('hospital_invoice', '2026-08-08', '**Patient:** Sam Parent\n**Amount due:** £9,680.13\n**Pay to:** Selden Medical Center, Beirut', 'INV')
    w.alert('TM06', [t])


@case('payee sharing addresses in a payment file', 'ESCALATE', 'ESC_MULE_ACTIVITY', policy='payments_fx')
def _(w):
    w.customer.update({'kind': 'business', 'business_activity': 'Imports furniture'})
    rows = []
    ts = []
    for i in range(6):
        amt = 400.0 + i
        ts.append(w.t('2026-08-1%d' % i, 'out', amt, 'Person %d' % i, channel='swift', country='Italy'))
        rows.append('| Person %d | Italy | %s | £%.2f |' % (i, ['1 Elm Way', '2 Oak Road'][i % 2], amt))
    w.doc('payment_file', '2026-08-09', '| Payee | Country | Address | Amount |\n|---|---|---|---|\n' + '\n'.join(rows), 'PAY')
    w.alert('TM04', ts)


@case('rule that does not run at this institution still gets a line (unknown alert data)', 'RFI')
def _(w):
    t = w.t('2026-08-10', 'in', 1500.00, 'Unknown Payer Ltd')
    w.alert('TM99', [t])


@case('held payment of £10,000+ with no invoice is not released', 'RFI', policy='payments_fx')
def _(w):
    w.customer.update({'kind': 'business', 'business_activity': 'Imports timber', 'name': 'Timber Co Ltd'})
    t = w.t('2026-08-10', 'out', 25000.00, 'New Supplier Co', channel='swift', country='Poland')
    w.held = t
    w.alert('TM01', [t], {'multiple': 2.4})


@case('consultancy invoice for a fresh-produce importer', 'ESCALATE', 'ESC_INVOICE_MISMATCH', policy='payments_fx')
def _(w):
    w.customer.update({'kind': 'business', 'business_activity': 'Imports fresh fruit and vegetables', 'name': 'Fresh Co Ltd'})
    t = w.t('2026-08-10', 'out', 13272.51, 'General Trading SARL', channel='swift', country='Lebanon', ref='INV 948')
    w.doc('supplier_invoices', '2026-08-05', '| Invoice | Goods | Amount |\n|---|---|---|\n| INV 948 | Business consultancy and market access services | £13,272.51 |', 'INV')
    w.alert('TM06', [t])


@case('verified group company funds a supplier payment', 'CLOSE', 'GROUP_COMPANY', policy='payments_fx')
def _(w):
    w.customer.update({'kind': 'business', 'business_activity': 'Imports electronic components', 'name': 'Talmore Electronics Ltd'})
    t = w.t('2026-08-10', 'in', 50398.90, 'Willey Trading Ltd', ref='INTERCOMPANY')
    w.doc('group_structure', '2026-03-01', '| Company | Owner | Share |\n|---|---|---|\n| Talmore Electronics Ltd | Harper Owner | 100% |\n| Willey Trading Ltd | Harper Owner | 100% |', 'GRP')
    w.alert('TM08', [t])


@case('third party claims to be a group company but is not in the structure', 'RFI', policy='payments_fx')
def _(w):
    w.customer.update({'kind': 'business', 'business_activity': 'Imports electronic components', 'name': 'Talmore Electronics Ltd'})
    t = w.t('2026-08-10', 'in', 50398.90, 'Stranger Holdings Ltd', ref='INTERCOMPANY')
    w.doc('group_structure', '2026-03-01', '| Company | Owner | Share |\n|---|---|---|\n| Talmore Electronics Ltd | Harper Owner | 100% |\n| Willey Trading Ltd | Harper Owner | 100% |', 'GRP')
    w.alert('TM08', [t])


@case('payer company dissolved before it paid', 'ESCALATE', 'ESC_UNEXPLAINED_FUNDS')
def _(w):
    ts = [w.t('2026-08-0%d' % d, 'in', 7006.67, 'Kelgate Trading Ltd', ref='CONSULTANCY') for d in (1, 2, 3)]
    o = w.t('2026-08-04', 'out', 18900.00, 'Harper Abroad', channel='swift', country='Turkey')
    w.doc('company_register_extract', '2026-08-05', '**Company:** Kelgate Trading Ltd\n**Status:** dissolved on 6 July 2025', 'REG')
    w.doc('support_chat', '2026-08-05', '**Customer:** It is a loan from a friend.', 'CHT')
    w.alert('TM02', ts + [o])


@case('collection for a group trip without the booking', 'RFI')
def _(w):
    ts = [w.t('2026-08-0%d' % (d % 9 + 1), 'in', 185.00, 'Friend %d' % d, ref='Lisbon trip') for d in range(8)]
    o = w.t('2026-08-10', 'out', 1480.00, 'Travel Co Ltd', ref='BK80177')
    w.alert('TM04', ts)
    w.alert('TM02', ts + [o])


@case('collection for a group trip with booking listing payers', 'CLOSE', 'COLLECTION_DOCUMENTED')
def _(w):
    ts = [w.t('2026-08-0%d' % (d % 9 + 1), 'in', 185.00, 'Friend %d' % d, ref='Lisbon trip') for d in range(8)]
    o = w.t('2026-08-10', 'out', 1665.00, 'Travel Co Ltd', ref='BK80177')
    w.doc('booking_confirmation', '2026-07-21', '**Booking reference:** BK80177\n**Lead traveller:** %s\n**Price:** £185.00 per person, £1,665.00 in total\nTravellers: %s' % (
        w.name, ', '.join([w.name] + ['Friend %d' % d for d in range(8)])), 'BKG')
    w.alert('TM04', ts)
    w.alert('TM02', ts + [o])


def run_all(verbose=True):
    tmp = tempfile.mkdtemp(prefix='tmedge_')
    results = []
    for i, (name, expect, code, policy, fn) in enumerate(CASES, start=1):
        w = World(i)
        fn(w)
        folder = os.path.join(tmp, 'case%02d' % i, policy)
        build(folder, [w], POLICY_PX if policy == 'payments_fx' else POLICY)
        out = os.path.join(tmp, 'case%02d.jsonl' % i)
        subprocess.check_call([os.path.join(SYSTEM, 'run'), folder, out])
        r = json.loads(open(out).readline())
        ok = r['verdict'] == expect and (code is None or r['reason_code'] == code)
        results.append((ok, name, expect, code, r))
        if verbose:
            print('%s  %-70s expect %-8s %-28s got %-8s %s' % ('PASS' if ok else 'FAIL', name[:70], expect, code or '', r['verdict'], r['reason_code']))
    shutil.rmtree(tmp, ignore_errors=True)
    n = sum(1 for r in results if r[0])
    print('\n%d/%d edge cases pass' % (n, len(results)))
    return results


if __name__ == '__main__':
    res = run_all()
    sys.exit(0 if all(r[0] for r in res) else 1)
