#!/usr/bin/env python3
"""Deterministic transaction-monitoring alert closer (Track 1).

No model, no network, no randomness: fixed rules over the institution folder.
"""
import json, os, re, sys
from datetime import date, datetime

VERDICT_OF = {
    'COLLECTION_DOCUMENTED': 'CLOSE', 'BUSINESS_RECORDS_RECONCILE': 'CLOSE', 'DOCUMENTED_EVENT': 'CLOSE',
    'INVOICE_MATCHES': 'CLOSE', 'OWN_ACCOUNT': 'CLOSE', 'GROUP_COMPANY': 'CLOSE', 'THIRD_PARTY_DOCUMENTED': 'CLOSE',
    'REFUND_OF_EARLIER_PAYMENT': 'CLOSE', 'RETURNING_CUSTOMER': 'CLOSE', 'LIST_MATCH_DIFFERENT_PARTY': 'CLOSE',
    'WITHIN_PROFILE': 'CLOSE',
    'RFI_PURPOSE_DOCUMENTS': 'RFI', 'RFI_BUSINESS_RECORDS': 'RFI', 'RFI_SOURCE_OF_FUNDS': 'RFI',
    'RFI_COUNTERPARTY_DETAILS': 'RFI', 'RFI_UPDATED_PROFILE': 'RFI',
    'ESC_MULE_ACTIVITY': 'ESCALATE', 'ESC_STRUCTURING': 'ESCALATE', 'ESC_UNEXPLAINED_FUNDS': 'ESCALATE',
    'ESC_PASS_THROUGH': 'ESCALATE', 'ESC_INVOICE_MISMATCH': 'ESCALATE', 'ESC_HIGH_RISK_CORRIDOR': 'ESCALATE',
    'ESC_ACCOUNT_MISUSE': 'ESCALATE', 'ESC_THIRD_PARTY_FUNDING': 'ESCALATE', 'ESC_EARLY_REDEMPTION': 'ESCALATE',
    'ESC_LISTED_PARTY': 'ESCALATE',
}

MONTHS = {m: i + 1 for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july',
                                          'august', 'september', 'october', 'november', 'december'])}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS['sept'] = 9


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def money(x):
    return '£{:,.2f}'.format(x)


AMT_RE = re.compile(r'(?:£|GBP|EUR|USD|€|\$|[A-Z]{3})\s?(\d{1,3}(?:[,\s]\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)(?!\d)'
                    r'|(\d{1,3}(?:,\d{3})+\.\d{2}|\d+\.\d{2})(?:\s?(?:GBP|EUR|USD|pounds))?')


def amounts_in(text):
    vals = []
    for m in AMT_RE.finditer(text):
        s = m.group(1) or m.group(2)
        if not s:
            continue
        s = s.replace(',', '').replace(' ', '')
        try:
            vals.append(float(s))
        except ValueError:
            pass
    return vals


def parse_date(s):
    """Parse ISO, '5 March 2026', 'March 5, 2026', '05/03/2026' (UK)."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.match(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\.?,?\s+(\d{4})', s)
    if m and m.group(2).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r'([A-Za-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})', s)
    if m and m.group(1).lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(1).lower()], int(m.group(2)))
        except ValueError:
            return None
    m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


DATE_IN_TEXT = re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|'
                          r'September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?,?\s+\d{4}', re.I)

STOP = {'ltd', 'limited', 'plc', 'llp', 'inc', 'the', 'and', 'co', 'company', 'gmbh', 'sa', 'sarl', 'bv', 'srl', 'llc',
        'of', 'client', 'account', '&'}


def norm(s):
    s = (s or '').lower().replace('’', "'")
    s = re.sub(r"[^a-z0-9 ]+", ' ', s)
    return ' '.join(s.split())


def name_key(s):
    return ' '.join(w for w in norm(s).split() if w not in STOP)


def name_in(name, text_norm):
    k = name_key(name)
    if not k:
        return False
    return (' ' + k + ' ') in (' ' + text_norm + ' ')


def digits(s):
    return re.sub(r'\D', '', s or '')


class Doc:
    def __init__(self, meta, text):
        self.id = meta.get('doc_id')
        self.type = (meta.get('type') or '').lower()
        self.title = meta.get('title') or ''
        self.dated = parse_date(meta.get('dated'))
        self.text = text
        self.low = text.lower()
        self.norm = norm(text)
        self.amounts = amounts_in(text)
        self.digits = digits(text)

    def has_amount(self, a, tol=0.011):
        return any(abs(x - a) <= tol for x in self.amounts)

    def field(self, label):
        m = re.search(r'\*\*' + re.escape(label) + r':?\*\*:?\s*(.+)', self.text, re.I)
        if not m:
            m = re.search(r'^' + re.escape(label) + r':\s*(.+)$', self.text, re.I | re.M)
        return m.group(1).strip() if m else None


class Data:
    def __init__(self, folder):
        self.folder = folder
        self.inst = os.path.basename(os.path.normpath(folder))
        self.policy = ''
        p = os.path.join(folder, 'POLICY.md')
        if os.path.exists(p):
            self.policy = open(p, encoding='utf-8').read()
        J = lambda n: load_jsonl(os.path.join(folder, n))
        self.cases = J('cases.jsonl')
        self.alerts = {a['alert_id']: a for a in J('alerts.jsonl')}
        self.customers = {c['customer_id']: c for c in J('customers.jsonl')}
        self.tx_by_cust = {}
        self.tx = {}
        for t in J('transactions.jsonl'):
            self.tx[t['transaction_id']] = t
            self.tx_by_cust.setdefault(t.get('customer_id'), []).append(t)
        for v in self.tx_by_cust.values():
            v.sort(key=lambda t: (t.get('booked_at') or '', t['transaction_id']))
        self.docs_by_cust = {}
        for e in J('evidence.jsonl'):
            fp = os.path.join(folder, e.get('file') or ('evidence/%s.md' % e.get('doc_id')))
            try:
                text = open(fp, encoding='utf-8').read()
            except OSError:
                text = ''
            self.docs_by_cust.setdefault(e.get('customer_id'), []).append(Doc(e, text))
        for v in self.docs_by_cust.values():
            v.sort(key=lambda d: d.id)
        self.prev = {}
        for r in J('previous_reviews.jsonl'):
            self.prev.setdefault(r.get('customer_id'), []).append(r)
        self.lst = {e['entry_id']: e for e in J('internal_list.jsonl')}
        self.high_risk = self._high_risk()

    def _high_risk(self):
        m = re.search(r'Higher-risk countries[^:]*:\s*(.+)', self.policy)
        if not m:
            return set()
        return {norm(x) for x in re.split(r',|\band\b', m.group(1).rstrip('.')) if x.strip()}


# ---------------------------------------------------------------- red flags
# (pattern, reason code, label). Patterns are matched on lower-cased text of
# customer-facing / staff documents. Order = priority.
RED_FLAGS = [
    (r"(send|sending|pass|passing|forward|forwarding|transfer|transferring|move|moving) (it|them|the money|the funds|this|that)? ?on\b|payments? assistant|money (transfer|processing) agent|keep \d+ ?%|my (manager|handler|boss) (needs|wants|said)",
     'ESC_MULE_ACTIVITY', 'customer describes receiving other people\'s money and sending it on'),
    (r"aggregat|cumulative|tallied|added together|below the (?:£[\d,\.]+ )?(?:reporting )?(?:threshold|limit)|under (?:£[\d,\.]+|the (?:threshold|limit))|exempt (?:them|him|her|me|us)? ?from|avoid (?:the )?(?:reporting|identity|id|verification|invoice)|breaking (?:down )?(?:the )?payments|split(?:ting)? (?:the )?(?:payments|deposits)",
     'ESC_STRUCTURING', 'customer asked how to keep amounts under a threshold'),
    (r"investing through mine|invest(?:ing)? for (?:a few people|them|others|friends|other people)|money to invest for them|cannot open an account here|on behalf of (?:my )?(?:friends|cousins|people)",
     'ESC_THIRD_PARTY_FUNDING', 'customer says the account is used for other people\'s money'),
    (r"unable or unwilling|could not (?:explain|justify)|couldn't explain|unable to (?:explain|justify|provide)|refused to (?:explain|provide)|declined to (?:explain|provide)|evasive",
     'ESC_UNEXPLAINED_FUNDS', 'staff record that the customer could not explain the activity'),
    (r"someone else (?:uses|controls|operates|has)|(?:my|a) (?:friend|cousin|partner|boyfriend|girlfriend) (?:uses|has|controls|operates) (?:my|the) (?:account|card|app|login)|gave (?:my|him|her|them) (?:my )?(?:login|card|pin|password|details)|let (?:him|her|them|a friend) use",
     'ESC_ACCOUNT_MISUSE', 'someone other than the customer appears to operate the account'),
]
SUSPICIOUS_TYPES = ('fraud_report', 'scam', 'police', 'recall')


def collect_red_flags(case_docs, cust, ctx):
    flags = []
    for d in case_docs:
        if d.type in ('due_diligence_summary', 'proof_of_address', 'company_register_extract',
                      'significant_control_register', 'management_accounts'):
            continue
        if any(s in d.type for s in SUSPICIOUS_TYPES) or re.search(r'push payment scam|authorised push payment|request to freeze|scam victim|were scammed|fraudulent', d.low):
            if 'fraud' in d.type or re.search(r'scam|fraud', d.low):
                flags.append(('ESC_MULE_ACTIVITY', d, 'the sending bank reports its customer paid this account as a scam victim'))
                continue
        if d.type == 'device_export':
            ids = sorted(set(re.findall(r'[A-Z]{2}-C\d+', d.text)))
            others = [i for i in ids if i != cust.get('customer_id')]
            countries = [c.strip() for c in re.findall(r'\|\s*([A-Za-z ,]+)\s*\|\s*$', d.text, re.M)]
            ctry = ' '.join(countries)
            if others:
                flags.append(('ESC_ACCOUNT_MISUSE', d, 'device %s is shared with %d other customer account(s) (%s)' % (
                    (re.findall(r'\|\s*([A-Za-z0-9-]+)\s*\|', d.text) or ['?'])[-0] if False else 'on file', len(others), ', '.join(others[:4]))))
            elif ctry and re.search(r',', ctry):
                flags.append(('ESC_ACCOUNT_MISUSE', d, 'the login device was used from several countries (%s)' % ctry.strip()))
            continue
        for pat, code, label in RED_FLAGS:
            if re.search(pat, d.low):
                # the institution's own wording ("pay it in", "send to") in procedures is not a flag
                if d.type in ('cash_handling_procedure', 'booking_confirmation', 'invoice', 'supplier_invoice',
                              'supplier_invoices', 'contract_schedule', 'payment_file', 'insurer_letter',
                              'solicitor_letter', 'loan_agreement', 'gift_letter', 'factoring_agreement'):
                    continue
                flags.append((code, d, label))
                break
    return flags


# ---------------------------------------------------------------- explanation
DOC_CODE = {
    'invoice': 'INVOICE_MATCHES', 'dealer_invoice': 'INVOICE_MATCHES', 'supplier_invoice': 'INVOICE_MATCHES',
    'supplier_invoices': 'INVOICE_MATCHES', 'consulting_contract': 'INVOICE_MATCHES', 'supply_contract': 'INVOICE_MATCHES',
    'contract_schedule': 'INVOICE_MATCHES', 'purchase_order': 'INVOICE_MATCHES', 'payment_file': 'INVOICE_MATCHES',
    'hospital_invoice': 'INVOICE_MATCHES', 'carrier_invoice': 'INVOICE_MATCHES', 'freight_invoices': 'INVOICE_MATCHES',
    'receipt': 'INVOICE_MATCHES', 'credit_note': 'REFUND_OF_EARLIER_PAYMENT',
    'solicitor_letter': 'DOCUMENTED_EVENT', 'insurer_letter': 'DOCUMENTED_EVENT', 'vehicle_sale_receipt': 'DOCUMENTED_EVENT',
    'sale_receipt': 'DOCUMENTED_EVENT', 'settlement_letter': 'DOCUMENTED_EVENT', 'completion_statement': 'DOCUMENTED_EVENT',
    'redundancy_letter': 'DOCUMENTED_EVENT', 'loan_agreement': 'DOCUMENTED_EVENT', 'deposit_return_letter': 'REFUND_OF_EARLIER_PAYMENT',
    'holding_deposit_receipt': 'DOCUMENTED_EVENT', 'cancellation_confirmation': 'REFUND_OF_EARLIER_PAYMENT',
    'venue_email': 'DOCUMENTED_EVENT', 'employment_contract': 'WITHIN_PROFILE', 'customer_email': 'DOCUMENTED_EVENT',
    'gift_letter': 'THIRD_PARTY_DOCUMENTED', 'factoring_agreement': 'THIRD_PARTY_DOCUMENTED', 'remittance_advice': 'THIRD_PARTY_DOCUMENTED',
    'group_structure': 'GROUP_COMPANY', 'email': 'THIRD_PARTY_DOCUMENTED',
    'booking_confirmation': 'COLLECTION_DOCUMENTED',
    'takings_book': 'BUSINESS_RECORDS_RECONCILE', 'cash_collection_reports': 'BUSINESS_RECORDS_RECONCILE',
    'cash_reconciliation': 'BUSINESS_RECORDS_RECONCILE', 'ticket_report': 'BUSINESS_RECORDS_RECONCILE',
    'management_accounts': 'BUSINESS_RECORDS_RECONCILE', 'bank_statement': 'OWN_ACCOUNT',
    'reverification_record': 'RETURNING_CUSTOMER', 'advert': 'DOCUMENTED_EVENT',
}
INVOICE_LIKE = {'invoice', 'dealer_invoice', 'supplier_invoice', 'supplier_invoices', 'purchase_order', 'hospital_invoice',
                'carrier_invoice', 'freight_invoices', 'payment_file', 'contract_schedule', 'consulting_contract', 'supply_contract'}
NON_EXPLAINING = {'due_diligence_summary', 'proof_of_address', 'contact_note', 'support_chat', 'staff_note',
                  'company_register_extract', 'significant_control_register', 'device_export', 'sending_bank_fraud_report',
                  'cash_handling_procedure', 'insurance_schedule', 'customer_letter'}
REF_TOKEN = re.compile(r'\b([A-Z]{2,}[ /-]?\d{3,}|\d{5,})\b')


def tx_date(t):
    return parse_date((t.get('booked_at') or '')[:10])


def ref_tokens(t):
    toks = []
    for m in REF_TOKEN.finditer(t.get('reference') or ''):
        toks.append(norm(m.group(1)))
    return toks


class Ctx:
    pass


def is_routine(t, cust):
    """Ordinary, profile-consistent movements that need no document."""
    ch = (t.get('channel') or '').lower()
    ref = (t.get('reference') or '').upper()
    cp = t.get('counterparty_name') or ''
    if t.get('direction') == 'out' and ch in ('card', 'direct_debit', 'standing_order'):
        return 'routine %s spending' % ch.replace('_', ' ')
    if t.get('direction') == 'in' and ref.startswith('SALARY') and cust.get('employer') and \
            name_key(cust['employer']) and name_key(cust['employer']) in name_key(cp + ' ' + ref):
        return 'salary from the declared employer %s' % cust['employer']
    if t.get('direction') == 'in' and 'CARD SETTLEMENT' in ref and cust.get('kind') == 'business':
        return 'card takings settled by the acquirer'
    return None


def doc_mentions_party(d, t):
    cp = t.get('counterparty_name') or ''
    if cp and name_in(cp, d.norm):
        return True
    for tok in ref_tokens(t):
        if tok and (' ' + tok + ' ') in (' ' + d.norm + ' '):
            return True
    acc = digits(t.get('counterparty_account'))
    if len(acc) >= 8 and acc[-8:] in d.digits:
        return True
    return False


def own_account_statement(t, cust, docs):
    """A bank statement on file in the customer's name showing the other account."""
    acc = digits(t.get('counterparty_account'))
    for d in docs:
        if d.type != 'bank_statement':
            continue
        holder = d.field('Account holder') or ''
        if not holder or name_key(holder) != name_key(cust.get('name')):
            continue
        tail = re.findall(r'ending (\d{3,})', d.low)
        if len(acc) >= 4 and (acc[-8:] in d.digits or any(acc.endswith(x) for x in tail)):
            return d
        if d.has_amount(t['amount_gbp']) or (t.get('amount') and d.has_amount(t['amount'])):
            return d
    return None


def statement_other_holder(t, cust, docs):
    for d in docs:
        if d.type != 'bank_statement':
            continue
        holder = d.field('Account holder') or ''
        if holder and name_key(holder) != name_key(cust.get('name')) and (
                d.has_amount(t['amount_gbp']) or doc_mentions_party(d, t)):
            return d, holder
    return None


def explain_tx(t, cust, docs, case_txs):
    """Return dict(code, docs, note) or dict(problem=...) or None."""
    r = is_routine(t, cust)
    if r:
        return {'code': 'WITHIN_PROFILE', 'docs': [], 'note': r, 'routine': True}
    cp = t.get('counterparty_name') or ''
    td = tx_date(t)
    own_name = cp and name_key(cp) == name_key(cust.get('name'))
    if own_name or re.search(r'OWN TRANSFER|TO SAVINGS|FROM SAVINGS|OWN ACCOUNT', (t.get('reference') or '').upper()):
        st = own_account_statement(t, cust, docs)
        if st:
            return {'code': 'OWN_ACCOUNT', 'docs': [st], 'note': '%s %s %s an account in the customer\'s own name, shown by statement %s' % (
                money(t['amount_gbp']), 'to' if t['direction'] == 'out' else 'from', 'Account at ' + (st.field('Bank') or 'another bank'), st.id)}
        oh = statement_other_holder(t, cust, docs)
        if oh:
            return {'problem': 'ESC_ACCOUNT_MISUSE', 'docs': [oh[0]], 'note': 'statement %s shows the account is held by %s, not the customer' % (oh[0].id, oh[1])}
    amts = [t['amount_gbp']] + ([t['amount']] if t.get('amount') not in (None, t['amount_gbp']) else [])
    best = None
    for d in docs:
        if d.type in NON_EXPLAINING:
            continue
        hit = any(d.has_amount(a) for a in amts)
        party = doc_mentions_party(d, t)
        coll = False
        if d.type == 'booking_confirmation' and t['direction'] == 'in' and cp and name_in(cp, d.norm):
            coll = True
        if d.type == 'booking_confirmation' and t['direction'] == 'out' and hit:
            coll = True
        if not (hit or coll):
            continue
        code = DOC_CODE.get(d.type, 'DOCUMENTED_EVENT')
        if 'REFUND' in (t.get('reference') or '').upper() or (t['direction'] == 'in' and re.search(r'\brefund', d.low)):
            code = 'REFUND_OF_EARLIER_PAYMENT'
        score = (2 if hit else 0) + (1 if party else 0) + (1 if coll else 0)
        issue = None
        if d.type in INVOICE_LIKE and t['direction'] == 'out' and d.dated and td and d.dated > td:
            issue = 'invoice %s is dated %s, after the payment on %s' % (d.id, d.dated.isoformat(), td.isoformat())
        if d.type in INVOICE_LIKE and t['direction'] == 'out' and not party and cp:
            pay_to = d.field('Pay to') or d.field('Supplier') or d.field('Payee') or ''
            if pay_to and name_key(cp) not in name_key(pay_to):
                issue = 'invoice %s names %s as payee, but the money went to %s' % (d.id, pay_to.split(',')[0], cp)
        cand = (score, d.id, d, code, issue)
        if best is None or cand[:2] > best[:2]:
            best = cand
    if best:
        score, _, d, code, issue = best
        if issue:
            return {'problem': 'ESC_INVOICE_MISMATCH', 'docs': [d], 'note': issue}
        if score >= 2:
            return {'code': code, 'docs': [d], 'note': '%s %s %s matches %s %s' % (
                money(t['amount_gbp']), 'from' if t['direction'] == 'in' else 'to', cp or t.get('channel'), d.type.replace('_', ' '), d.id)}
        if code == 'COLLECTION_DOCUMENTED':
            return {'code': code, 'docs': [d], 'note': '%s is a named participant on %s' % (cp, d.id)}
    # sum match: one document covers several alerted transactions to/from the same party
    same = [x for x in case_txs if x.get('counterparty_name') == cp and x['direction'] == t['direction']]
    if len(same) > 1:
        tot = round(sum(x['amount_gbp'] for x in same), 2)
        for d in docs:
            if d.type in NON_EXPLAINING:
                continue
            if d.has_amount(tot):
                return {'code': DOC_CODE.get(d.type, 'INVOICE_MATCHES'), 'docs': [d], 'sum': True,
                        'note': '%d payments %s %s total %s, matching %s' % (len(same), 'from' if t['direction'] == 'in' else 'to', cp, money(tot), d.id)}
    return None


# ---------------------------------------------------------------- internal list
MONTH_YEAR = re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', re.I)


def register_rows(d):
    """Markdown table rows -> list of dict(header->cell)."""
    rows, header = [], None
    for line in d.text.splitlines():
        line = line.strip()
        if not line.startswith('|'):
            header = None if not line else header
            continue
        cells = [c.strip() for c in line.strip('|').split('|')]
        if all(re.fullmatch(r':?-{2,}:?', c) for c in cells if c):
            continue
        if header is None:
            header = [c.lower() for c in cells]
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def check_list_match(alert, case_txs, docs, data):
    m = alert.get('measured') or {}
    entry = data.lst.get(m.get('list_entry'))
    on = str(m.get('matched_on') or '').lower()
    if not entry:
        return ('RFI_COUNTERPARTY_DETAILS', [], 'the internal list entry %s could not be found on file' % m.get('list_entry'), None)
    eid = entry['entry_id']
    lname = entry.get('name') or ''
    ldob = parse_date(entry.get('date_of_birth'))
    t = None
    for tid in alert.get('transaction_ids') or []:
        t = data.tx.get(tid) or t
    td = tx_date(t) if t else None
    # 1. a document on file gives the counterparty's date of birth
    for d in docs:
        if d.type in ('due_diligence_summary', 'proof_of_address'):
            continue
        if lname and name_in(lname, d.norm):
            mm = re.search(re.escape(lname) + r'[^.\n|]{0,40}?\bborn\s+(?:on\s+)?([0-9]{1,2}\s+[A-Za-z]+\s+\d{4}|\d{4}-\d{2}-\d{2}|[A-Za-z]+\s+\d{4})', d.text, re.I)
            if mm:
                dob = parse_date(mm.group(1))
                if dob and ldob:
                    if dob != ldob:
                        return ('LIST_MATCH_DIFFERENT_PARTY', [d], '%s gives %s\'s date of birth as %s, but list entry %s is born %s' % (
                            d.id, lname, dob.strftime('%-d %B %Y'), eid, ldob.strftime('%-d %B %Y')), eid)
                    return ('ESC_LISTED_PARTY', [d], '%s gives %s\'s date of birth as %s, the same as list entry %s' % (
                        d.id, lname, dob.strftime('%-d %B %Y'), eid), eid)
                my = MONTH_YEAR.search(mm.group(1))
                if my and ldob:
                    same = (MONTHS[my.group(1).lower()], int(my.group(2))) == (ldob.month, ldob.year)
                    if not same:
                        return ('LIST_MATCH_DIFFERENT_PARTY', [d], '%s gives %s as born %s, but list entry %s is born %s' % (
                            d.id, lname, mm.group(1), eid, ldob.strftime('%B %Y')), eid)
    # 2. company registers: is the listed person an officer / controller on the payment date?
    regs = [d for d in docs if d.type in ('company_register_extract', 'significant_control_register')]
    cp = (t or {}).get('counterparty_name') or ''
    relevant = [d for d in regs if not (d.field('Company') and name_key(d.field('Company')) == name_key(data.customers.get((t or {}).get('customer_id'), {}).get('name')))]
    active, ended, seen_docs, other_people = [], [], [], []
    for d in relevant:
        for row in register_rows(d):
            person = row.get('officer') or row.get('person') or row.get('person with significant control') or ''
            if not person:
                continue
            born = row.get('born') or ''
            is_listed = lname and name_key(person) == name_key(lname)
            if not is_listed:
                other_people.append((person, d))
                continue
            seen_docs.append(d)
            if born and ldob:
                my = MONTH_YEAR.search(born)
                if my and (MONTHS[my.group(1).lower()], int(my.group(2))) != (ldob.month, ldob.year):
                    ended.append((d, '%s in %s is born %s, not %s like list entry %s' % (person, d.id, born, ldob.strftime('%B %Y'), eid)))
                    continue
            end = parse_date(row.get('resigned') or row.get('ceased') or '')
            role = row.get('role') or ('controller' if 'control' in row else 'officer')
            if end and td and end < td:
                ended.append((d, '%s stopped being %s on %s, before the payment on %s (%s)' % (person, role.lower(), end.strftime('%-d %B %Y'), td.strftime('%-d %B %Y'), d.id)))
            else:
                active.append((d, '%s was still %s of %s on %s (%s%s)' % (
                    person, role.lower() if role else 'in control', cp or 'the counterparty', td.strftime('%-d %B %Y') if td else 'the payment date', d.id,
                    ', ceased %s' % end.strftime('%-d %B %Y') if end else '')))
    if active:
        return ('ESC_LISTED_PARTY', [x[0] for x in active], '; '.join(x[1] for x in active), eid)
    if ended:
        return ('LIST_MATCH_DIFFERENT_PARTY', [x[0] for x in ended], '; '.join(x[1] for x in ended), eid)
    # 3. address-only match: the counterparty's register shows a different unit and different people
    if 'address' in on and relevant:
        laddr = norm(entry.get('address'))
        for d in relevant:
            office = norm(d.field('Registered office') or '')
            if office and laddr and office != laddr and other_people:
                ppl = sorted(set(p for p, dd in other_people if dd is d))
                if ppl:
                    return ('LIST_MATCH_DIFFERENT_PARTY', [d], '%s shows %s at %s, not %s, run by %s rather than the listed %s' % (
                        d.id, cp or 'the counterparty', d.field('Registered office'), entry.get('address'), ', '.join(ppl), lname), eid)
            if office and laddr and office == laddr:
                return ('ESC_LISTED_PARTY', [d], '%s shows %s at the listed address %s' % (d.id, cp, entry.get('address')), eid)
    return ('RFI_COUNTERPARTY_DETAILS', [], 'nothing on file shows whether %s is the %s on list entry %s (%s)' % (
        cp or lname, lname, eid, entry.get('reason', '').rstrip('.')), eid)


# ---------------------------------------------------------------- policy
def policy_settings(data):
    p = data.policy
    s = {'own_rfi_multiple': 5.0, 'invoice_threshold': None}
    m = re.search(r'own accounts explain activity at (\d+(?:\.\d+)?) times', p)
    if m:
        s['own_rfi_multiple'] = float(m.group(1))
    m = re.search(r'Payments of £([\d,]+(?:\.\d+)?) or more to anyone other than the client need an invoice', p)
    if m:
        s['invoice_threshold'] = float(m.group(1).replace(',', ''))
    s['rules_run'] = sorted(set(re.findall(r'^\|\s*(TM\d+)\s*\|', p, re.M)))
    return s


RULE_WORD = {'TM01': 'activity above profile', 'TM02': 'rapid movement of funds', 'TM03': 'repeated transactions below a threshold',
             'TM04': 'many-to-one / one-to-many payments', 'TM05': 'large cash', 'TM06': 'higher-risk corridor',
             'TM07': 'dormant account reactivation', 'TM08': 'third-party funding or payout', 'TM10': 'early fund redemption',
             'TM22': 'internal list match'}

RFI_ASK = {
    'RFI_SOURCE_OF_FUNDS': 'proof of where the money came from (for example a sale agreement, loan agreement, payslip or bank statement)',
    'RFI_PURPOSE_DOCUMENTS': 'documents showing what the payments were for (an invoice, contract or receipt naming the payee and amount)',
    'RFI_BUSINESS_RECORDS': 'the business records behind the activity (takings records, sales ledger or management accounts for the period)',
    'RFI_COUNTERPARTY_DETAILS': 'who the counterparty is, their relationship to the customer and what the payment was for',
    'RFI_UPDATED_PROFILE': 'an updated expected monthly income or payment volume, with evidence of the new level',
}

ESC_PRIORITY = ['ESC_LISTED_PARTY', 'ESC_MULE_ACTIVITY', 'ESC_STRUCTURING', 'ESC_ACCOUNT_MISUSE', 'ESC_INVOICE_MISMATCH',
                'ESC_THIRD_PARTY_FUNDING', 'ESC_EARLY_REDEMPTION', 'ESC_PASS_THROUGH', 'ESC_HIGH_RISK_CORRIDOR',
                'ESC_UNEXPLAINED_FUNDS']


def fmt_tx(t):
    return '%s %s %s on %s' % (money(t['amount_gbp']), 'from' if t['direction'] == 'in' else 'to',
                               t.get('counterparty_name') or (t.get('channel') or '').replace('_', ' '), (t.get('booked_at') or '')[:10])


def decide(case, data, settings):
    cust = data.customers.get(case.get('customer_id'), {'customer_id': case.get('customer_id'), 'name': ''})
    docs = data.docs_by_cust.get(case.get('customer_id'), [])
    alerts = [data.alerts[a] for a in case.get('alert_ids') or [] if a in data.alerts]
    rules = sorted(set(a['rule_id'] for a in alerts))
    trace = {'checks': [], 'flags': [], 'rules': rules}
    tids = []
    for a in alerts:
        for tid in a.get('transaction_ids') or []:
            if tid not in tids and tid in data.tx:
                tids.append(tid)
    txs = sorted((data.tx[t] for t in tids), key=lambda t: (t.get('booked_at') or '', t['transaction_id']))
    cname = cust.get('name') or 'the customer'
    esc, rfi, closes = [], [], []      # (code, evidence ids, sentence)

    if len(alerts) != len(case.get('alert_ids') or []):
        rfi.append(('RFI_PURPOSE_DOCUMENTS', [], 'some alerts in the case could not be found, so the activity cannot be confirmed'))

    # ---- red flags in notes, chats and reports
    for code, d, label in collect_red_flags(docs, cust, None):
        esc.append((code, [d.id], '%s %s: %s' % (d.type.replace('_', ' '), d.id, label)))
        trace['flags'].append({'code': code, 'doc': d.id, 'label': label})

    # ---- internal list
    list_ok = set()
    for a in alerts:
        if a['rule_id'] != 'TM22':
            continue
        code, ds, why, eid = check_list_match(a, txs, docs, data)
        ev = [x.id for x in ds] + ([eid] if eid else []) + list(a.get('transaction_ids') or [])
        trace['checks'].append({'alert': a['alert_id'], 'rule': 'TM22', 'result': code, 'note': why, 'evidence': ev})
        if VERDICT_OF[code] == 'ESCALATE':
            esc.append((code, ev, why))
        elif VERDICT_OF[code] == 'RFI':
            rfi.append((code, ev, why))
        else:
            closes.append((code, ev, why))
            list_ok.update(a.get('transaction_ids') or [])

    # ---- dormant reactivation: who is operating the account?
    reverified = None
    if 'TM07' in rules:
        for d in docs:
            if d.type == 'reverification_record':
                if re.search(r'new device|different device|not (?:previously )?registered|failed|could not be (?:verified|confirmed)|did not match|mismatch', d.low):
                    esc.append(('ESC_ACCOUNT_MISUSE', [d.id], 'reverification record %s does not confirm the customer: the check used a new device or failed' % d.id))
                else:
                    reverified = d
        trace['checks'].append({'rule': 'TM07', 'result': 'reverified' if reverified else 'not reverified',
                                'note': ('identity re-verified in %s' % reverified.id) if reverified else 'no re-verification on file',
                                'evidence': [reverified.id] if reverified else []})

    # ---- per transaction explanation
    unexplained, explained, own_used = [], [], False
    for t in txs:
        if t['transaction_id'] in list_ok:
            ex = explain_tx(t, cust, docs, txs)
            if not ex or 'problem' in ex:
                explained.append((t, {'code': 'LIST_MATCH_DIFFERENT_PARTY', 'docs': [], 'note': 'counterparty shown not to be the listed party'}))
                continue
        else:
            ex = explain_tx(t, cust, docs, txs)
        if ex is None and t.get('channel') == 'cash_deposit':
            # cash paid back in after an earlier withdrawal of the same amount
            for o in data.tx_by_cust.get(case.get('customer_id'), []):
                if o.get('channel') == 'cash_withdrawal' and abs(o['amount_gbp'] - t['amount_gbp']) < 0.01 and \
                        (o.get('booked_at') or '') < (t.get('booked_at') or ''):
                    ex = {'code': 'WITHIN_PROFILE', 'docs': [d for d in docs if d.type == 'support_chat' and d.has_amount(t['amount_gbp'])],
                          'note': '%s cash paid back in matches the %s cash withdrawal of %s on %s' % (
                              money(t['amount_gbp']), 'same-amount', money(o['amount_gbp']), o['booked_at'][:10]), 'extra': [o['transaction_id']]}
                    break
        if ex is None and 'TM07' in rules and reverified and t['direction'] == 'in' and \
                name_key(t.get('counterparty_name')) == name_key(cust.get('name')):
            st = own_account_statement(t, cust, docs)
            if st:
                ex = {'code': 'OWN_ACCOUNT', 'docs': [st], 'note': 'own funds moved back from %s' % st.id}
        if ex is None:
            unexplained.append(t)
            trace['checks'].append({'tx': t['transaction_id'], 'result': 'UNEXPLAINED', 'note': fmt_tx(t) + ' has no matching document'})
        elif 'problem' in ex:
            esc.append((ex['problem'], [d.id for d in ex['docs']] + [t['transaction_id']], ex['note']))
            trace['checks'].append({'tx': t['transaction_id'], 'result': ex['problem'], 'note': ex['note'], 'evidence': [d.id for d in ex['docs']]})
        else:
            explained.append((t, ex))
            if ex['code'] == 'OWN_ACCOUNT':
                own_used = True
            trace['checks'].append({'tx': t['transaction_id'], 'result': ex['code'], 'note': ex['note'], 'evidence': [d.id for d in ex['docs']]})

    # ---- held payment at a payments firm needs an invoice above the threshold
    held = case.get('held_payment_id')
    if held and held in data.tx and settings.get('invoice_threshold'):
        h = data.tx[held]
        if h['amount_gbp'] >= settings['invoice_threshold'] and name_key(h.get('counterparty_name')) != name_key(cname):
            ok = [e for (t, e) in explained if t['transaction_id'] == held and e['code'] in ('INVOICE_MATCHES', 'GROUP_COMPANY', 'THIRD_PARTY_DOCUMENTED', 'REFUND_OF_EARLIER_PAYMENT') and e['docs']]
            if not ok and h not in unexplained:
                unexplained.append(h)

    # ---- TM10: a documented reason to sell
    if 'TM10' in rules and not esc:
        reason_docs = [d for d in docs if d.type in ('redundancy_letter', 'customer_email', 'completion_statement') and
                       re.search(r'redundan|sell|withdraw|house|completion|deposit', d.low)]
        red = [t for t in unexplained if t.get('channel') in ('fund_redemption',) or 'TM10' in rules]
        if reason_docs:
            for t in list(unexplained):
                if t.get('channel') in ('fund_redemption', 'fund_subscription'):
                    unexplained.remove(t)
                    explained.append((t, {'code': 'DOCUMENTED_EVENT', 'docs': reason_docs[:2], 'note': 'sale explained by %s' % ', '.join(d.id for d in reason_docs[:2])}))
            closes.append(('DOCUMENTED_EVENT', [d.id for d in reason_docs[:2]], 'the early sale is explained by %s' % ', '.join(
                '%s %s' % (d.type.replace('_', ' '), d.id) for d in reason_docs[:2])))
        else:
            fund_tx = [t for t in txs if t.get('channel') in ('fund_redemption', 'fund_subscription')]
            if fund_tx and not any(t in unexplained for t in fund_tx):
                pass
            elif not fund_tx and not unexplained:
                unexplained.extend(txs[:1])

    # ---- aggregate
    ev_tx = [t['transaction_id'] for t in txs]
    if esc:
        esc.sort(key=lambda e: ESC_PRIORITY.index(e[0]) if e[0] in ESC_PRIORITY else 99)
        return finish('ESCALATE', esc[0][0], esc, explained, unexplained, txs, case, cust, rules, trace)
    if unexplained:
        code = fallback_code(rules, unexplained, cust, docs, txs)
        if VERDICT_OF[code] == 'ESCALATE':
            return finish('ESCALATE', code, [(code, [], '')], explained, unexplained, txs, case, cust, rules, trace)
        rfi.insert(0, (code, [], ''))
    if rfi:
        return finish('RFI', rfi[0][0], rfi, explained, unexplained, txs, case, cust, rules, trace)
    # everything explained
    if own_used and 'TM01' in rules:
        mult = max([(a.get('measured') or {}).get('multiple') or 0 for a in alerts if a['rule_id'] == 'TM01'] or [0])
        if mult >= settings['own_rfi_multiple']:
            return finish('RFI', 'RFI_UPDATED_PROFILE', [('RFI_UPDATED_PROFILE', [], 'own-account transfers bring activity to %.1f times the declared level, at or above the policy limit of %g times' % (mult, settings['own_rfi_multiple']))],
                          explained, unexplained, txs, case, cust, rules, trace)
    if 'TM07' in rules and reverified:
        closes.append(('RETURNING_CUSTOMER', [reverified.id], 'identity re-verified in %s' % reverified.id))
    codes = [e['code'] for (t, e) in explained if not e.get('routine')] + [c[0] for c in closes]
    if not codes:
        codes = ['WITHIN_PROFILE']
    pri = ['LIST_MATCH_DIFFERENT_PARTY', 'COLLECTION_DOCUMENTED', 'BUSINESS_RECORDS_RECONCILE', 'REFUND_OF_EARLIER_PAYMENT',
           'GROUP_COMPANY', 'THIRD_PARTY_DOCUMENTED', 'INVOICE_MATCHES', 'DOCUMENTED_EVENT', 'OWN_ACCOUNT', 'RETURNING_CUSTOMER', 'WITHIN_PROFILE']
    if 'TM07' in rules and reverified and all(c in ('RETURNING_CUSTOMER', 'WITHIN_PROFILE', 'OWN_ACCOUNT') for c in codes):
        main = 'RETURNING_CUSTOMER'
    else:
        main = sorted(set(codes), key=lambda c: (-codes.count(c) if c not in ('LIST_MATCH_DIFFERENT_PARTY',) else -999, pri.index(c)))[0]
    return finish('CLOSE', main, closes, explained, unexplained, txs, case, cust, rules, trace)


def fallback_code(rules, unexplained, cust, docs, txs):
    biz = cust.get('kind') == 'business'
    if 'TM03' in rules:
        return 'ESC_STRUCTURING'
    if 'TM10' in rules:
        return 'ESC_EARLY_REDEMPTION'
    chats = [d for d in docs if d.type in ('support_chat', 'staff_note', 'customer_email', 'customer_letter', 'email')]
    outs = [t for t in unexplained if t['direction'] == 'out']
    ins = [t for t in unexplained if t['direction'] == 'in']
    if 'TM02' in rules and ('TM04' in rules or len(set(t.get('counterparty_name') for t in ins)) > 3):
        return 'ESC_MULE_ACTIVITY'
    if 'TM02' in rules and 'TM08' in rules:
        return 'ESC_THIRD_PARTY_FUNDING'
    if 'TM06' in rules and any(norm(t.get('counterparty_country')) for t in unexplained):
        if chats:
            return 'RFI_PURPOSE_DOCUMENTS'
        return 'ESC_HIGH_RISK_CORRIDOR'
    if 'TM02' in rules:
        return 'ESC_UNEXPLAINED_FUNDS'
    if 'TM08' in rules:
        return 'RFI_COUNTERPARTY_DETAILS'
    if 'TM04' in rules:
        return 'RFI_BUSINESS_RECORDS' if biz else 'RFI_COUNTERPARTY_DETAILS'
    if 'TM22' in rules and not ins:
        return 'RFI_PURPOSE_DOCUMENTS'
    if outs and not ins:
        return 'RFI_PURPOSE_DOCUMENTS'
    return 'RFI_BUSINESS_RECORDS' if biz else 'RFI_SOURCE_OF_FUNDS'


def _uniq(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


def finish(verdict, code, items, explained, unexplained, txs, case, cust, rules, trace):
    cname = cust.get('name') or 'The customer'
    rule_txt = ', '.join('%s (%s)' % (r, RULE_WORD.get(r, r)) for r in rules)
    sents, ev = [], []
    main_items = [i for i in items if i[0] == code] or items[:1]
    if verdict == 'ESCALATE':
        lead = [i for i in main_items if i[2]]
        if lead:
            sents.append('%s: %s.' % (cname, lead[0][2][0].lower() + lead[0][2][1:] if lead[0][2] else ''))
            ev += lead[0][1]
            for extra in [i for i in items if i[2] and i is not lead[0]][:1]:
                sents.append('Also, %s.' % extra[2])
                ev += extra[1]
        if unexplained:
            tot = sum(t['amount_gbp'] for t in unexplained)
            sents.append('%d alerted transaction(s) totalling %s have no supporting document, including %s.' % (
                len(unexplained), money(tot), '; '.join(fmt_tx(t) for t in unexplained[:2])))
            ev += [t['transaction_id'] for t in unexplained[:6]]
        if not lead and not unexplained:
            sents.append('%s: the alerts (%s) are not explained by the documents on file.' % (cname, rule_txt))
        sents.append('There are grounds for suspicion (%s), so the case goes to the MLRO rather than to the customer.' % code)
    elif verdict == 'RFI':
        lead = [i for i in main_items if i[2]]
        if lead:
            sents.append('%s: %s.' % (cname, lead[0][2]))
            ev += lead[0][1]
        if unexplained:
            tot = sum(t['amount_gbp'] for t in unexplained)
            sents.append('The alerts (%s) are driven by %s totalling %s that no document on file explains (%s).' % (
                rule_txt, 'transaction' if len(unexplained) == 1 else '%d transactions' % len(unexplained), money(tot),
                '; '.join(fmt_tx(t) for t in unexplained[:2])))
            ev += [t['transaction_id'] for t in unexplained[:6]]
        good = [(t, e) for (t, e) in explained if not e.get('routine')]
        if good:
            sents.append('Already explained: %s.' % '; '.join(e['note'] for (t, e) in good[:2]))
            for t, e in good[:3]:
                ev += [d.id for d in e['docs']]
        sents.append('Nothing on file suggests crime yet, so ask %s for %s.' % (cname, RFI_ASK.get(code, 'the supporting documents')))
    else:
        good = [(t, e) for (t, e) in explained if not e.get('routine')]
        main = [(t, e) for (t, e) in good if e['code'] == code] or good
        notes = _uniq([e['note'] for (t, e) in main])
        for c in [i for i in items if i[0] == code and i[2]][:1]:
            sents.append('%s: %s.' % (cname, c[2]))
            ev += c[1]
        if notes:
            sents.append(('%s: ' % cname if not sents else '') + '; '.join(notes[:3]) + ('; and %d more' % (len(notes) - 3) if len(notes) > 3 else '') + '.')
        for t, e in good:
            ev += [d.id for d in e['docs']] + [t['transaction_id']] + e.get('extra', [])
        for c in items:
            ev += c[1]
        routine = [(t, e) for (t, e) in explained if e.get('routine')]
        if routine:
            sents.append('The other alerted items are %s.' % '; '.join(_uniq(e['note'] for (t, e) in routine)[:2]))
        sents.append('Every alert in the case (%s) is explained by the evidence, so the case is closed as %s.' % (rule_txt, code))
    if not ev:
        ev = [t['transaction_id'] for t in txs[:6]]
    reason = ' '.join(s.strip() for s in sents[:4] if s.strip())
    trace['verdict'] = verdict
    trace['code'] = code
    return {'case_id': case['case_id'], 'alert_ids': list(case.get('alert_ids') or []), 'verdict': verdict,
            'reason_code': code, 'reason': reason, 'evidence': _uniq(ev)[:15]}, trace


def run(folder, out_path, trace_path=None):
    data = Data(folder)
    settings = policy_settings(data)
    rows, traces = [], {}
    for case in data.cases:
        try:
            row, tr = decide(case, data, settings)
        except Exception as exc:  # fail safe: never close what we could not process
            row = {'case_id': case.get('case_id'), 'alert_ids': list(case.get('alert_ids') or []), 'verdict': 'ESCALATE',
                   'reason_code': 'ESC_UNEXPLAINED_FUNDS',
                   'reason': 'The case could not be processed automatically (%s), so the activity is unexplained and goes to the MLRO.' % type(exc).__name__,
                   'evidence': []}
            tr = {'error': repr(exc)}
        assert VERDICT_OF[row['reason_code']] == row['verdict']
        rows.append(row)
        traces[case.get('case_id')] = tr
    d = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(d, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=False) + '\n')
    if trace_path:
        with open(trace_path, 'w', encoding='utf-8') as f:
            json.dump(traces, f, ensure_ascii=False, sort_keys=True, default=str)
    return rows


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write('usage: run <institution folder> <output file>\n')
        sys.exit(2)
    tp = os.environ.get('TM_TRACE')
    run(sys.argv[1], sys.argv[2], tp)
