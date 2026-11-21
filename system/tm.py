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
    (r"\bexempt|structur(?:e|ing) (?:the |their |my |our )?(?:payments|deposits|top-?ups|transactions)|(?:instal(?:l)?ments|increments|amounts|deposits|payments|top-?ups) (?:of )?(?:less than|below|under|beneath) £|keep(?:ing)? (?:each |every |individual |the |their |my )?(?:cash )?(?:deposits?|payments?|top-?ups?|amounts?|transactions?) (?:below|under|beneath|less than)|aggregat|cumulative|tallied|added together|below the (?:£[\d,\.]+ )?(?:reporting )?(?:threshold|limit)|under (?:£[\d,\.]+|the (?:threshold|limit))|exempt (?:them|him|her|me|us)? ?from|avoid (?:the )?(?:reporting|identity|id|verification|invoice)|breaking (?:down )?(?:the )?payments|split(?:ting)? (?:the )?(?:payments|deposits)",
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
            return {'code': 'OWN_ACCOUNT', 'docs': [st], 'note': '%s %s %s\'s own account at %s (statement %s, held in their name)' % (
                money(t['amount_gbp']), 'went to' if t['direction'] == 'out' else 'came from', cust.get('name'), st.field('Bank') or 'another bank', st.id)}
        oh = statement_other_holder(t, cust, docs)
        if oh:
            return {'problem': 'ESC_ACCOUNT_MISUSE', 'docs': [oh[0]], 'note': 'statement %s shows the account is held by %s, not the customer' % (oh[0].id, oh[1])}
    g = group_link(t, cust, docs)
    if g:
        return {'code': 'GROUP_COMPANY', 'docs': [g], 'note': '%s is in the same group as %s according to group structure %s' % (cp, cust.get('name'), g.id)}
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
        if issue is None and d.type in INVOICE_LIKE:
            gm = goods_mismatch(d, cust)
            if gm:
                issue = gm
        cand = (score, d.id, d, code, issue)
        if best is None or cand[:2] > best[:2]:
            best = cand
    if best:
        score, _, d, code, issue = best
        if issue:
            return {'problem': 'ESC_INVOICE_MISMATCH', 'docs': [d], 'note': issue}
        if score >= 2:
            return {'code': code, 'docs': [d], 'note': '%s %s %s matches %s %s' % (
                money(t['amount_gbp']), 'from' if t['direction'] == 'in' else 'to', cp or (t.get('channel') or '').replace('_', ' '), d.type.replace('_', ' '), d.id)}
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
            mm = re.search(re.escape(lname) + r'[^.\n|]{0,40}?(?:\bborn|\bDOB|\bD\.O\.B\.?|date of birth)\s*(?:on|:|-)?\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\.?,?\s+\d{4}|[A-Za-z]+\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Za-z]+\s+\d{4})', d.text, re.I)
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
    for code, ids, label in structural_flags(docs, cust, txs, data):
        esc.append((code, ids, label))
        trace['flags'].append({'code': code, 'doc': ids[0], 'label': label})
    for code, d, label in collect_red_flags(docs, cust, None) + payment_file_flags(docs):
        esc.append((code, [d.id], '%s %s: %s' % (d.type.replace('_', ' '), d.id, label)))
        trace['flags'].append({'code': code, 'doc': d.id, 'label': label})

    for d in docs:
        if d.type in INVOICE_LIKE:
            gm = goods_mismatch(d, cust)
            if gm:
                esc.append(('ESC_INVOICE_MISMATCH', [d.id], gm))
                trace['flags'].append({'code': 'ESC_INVOICE_MISMATCH', 'doc': d.id, 'label': gm})

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
    max_amt = {}
    for a in alerts:
        amts = [data.tx[x]['amount_gbp'] for x in a.get('transaction_ids') or [] if x in data.tx]
        for x in a.get('transaction_ids') or []:
            if amts:
                max_amt[x] = max(max_amt.get(x, 0), max(amts))
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
        if ex is None and t['direction'] == 'in' and name_key(t.get('counterparty_name')) == name_key(cust.get('name')):
            ex = own_funding(t, cust, docs, data)
        if ex is None and 'TM07' in rules and reverified and t['direction'] == 'in' and \
                name_key(t.get('counterparty_name')) == name_key(cust.get('name')):
            st = own_account_statement(t, cust, docs)
            if st:
                ex = {'code': 'OWN_ACCOUNT', 'docs': [st], 'note': 'own funds moved back from %s' % st.id}
        if ex is None and t['direction'] == 'out' and t['transaction_id'] != case.get('held_payment_id') and not any(
                a['rule_id'] in ('TM03', 'TM06', 'TM22') and t['transaction_id'] in (a.get('transaction_ids') or []) for a in alerts):
            ex = established_payee(t, cust, data, case)
        if ex is None:
            mx = max_amt.get(t['transaction_id'], 0)
            own_small = name_key(t.get('counterparty_name')) == name_key(cust.get('name')) and \
                t['amount_gbp'] <= max((cust.get('declared') or {}).get('monthly_income_gbp') or 0,
                                     ((cust.get('declared') or {}).get('annual_turnover_gbp') or 0) / 12.0, 2000) and t["amount_gbp"] < 0.5 * mx
            if (own_small or (t['amount_gbp'] < 1000 and t['amount_gbp'] < 0.1 * mx)) and not any(
                    a['rule_id'] in ('TM03', 'TM04', 'TM22', 'TM06') and t['transaction_id'] in (a.get('transaction_ids') or []) for a in alerts):
                ex = {'code': 'WITHIN_PROFILE', 'docs': [], 'routine': True,
                      'note': 'small everyday transfers such as %s are minor next to the %s that drove the alert' % (fmt_tx(t), money(mx))}
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
            ctx_docs = [d.id for d in docs if d.type in ('support_chat', 'staff_note', 'customer_email', 'email', 'company_register_extract') and
                        (d.type != 'company_register_extract' or name_key(d.field('Company') or '') != name_key(cname))]
            return finish('ESCALATE', code, [(code, ctx_docs[:3], '')], explained, unexplained, txs, case, cust, rules, trace)
        if any(r[0] == 'RFI_COUNTERPARTY_DETAILS' for r in rfi):
            rfi.append((code, [], ''))
        else:
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
    """No document explains these transactions and no red flag was found: ask (RFI),
    except where the shape of the activity is itself a recognised typology."""
    biz = cust.get('kind') == 'business'
    chats = [d for d in docs if d.type in ('support_chat', 'staff_note', 'customer_email', 'customer_letter', 'email')]
    outs = [t for t in unexplained if t['direction'] == 'out']
    ins = [t for t in unexplained if t['direction'] == 'in']
    third_in = sorted(set(t.get('counterparty_name') or '' for t in ins if name_key(t.get('counterparty_name')) != name_key(cust.get('name'))))
    out_people = sorted(set(t.get('counterparty_name') or '' for t in outs))
    same_amt = len(outs) >= 3 and len(set(round(t['amount_gbp'], 0) for t in outs)) == 1 and len(out_people) >= 2
    if 'TM06' in rules and any(norm(t.get('counterparty_country')) for t in unexplained):
        if (third_in and outs) or same_amt:
            return 'ESC_HIGH_RISK_CORRIDOR'
        return 'RFI_PURPOSE_DOCUMENTS'
    # many unrelated people paying in for varied reasons, then moved on = mule pattern
    if len(third_in) >= 4 and ('TM02' in rules or outs) and not collection_like(ins):
        return 'ESC_MULE_ACTIVITY'
    if 'TM22' in rules:
        return 'RFI_COUNTERPARTY_DETAILS'
    if 'TM03' in rules:
        # amounts just under a limit with no record behind them: ask for the invoices / takings records
        return 'RFI_PURPOSE_DOCUMENTS' if outs else ('RFI_BUSINESS_RECORDS' if biz else 'RFI_SOURCE_OF_FUNDS')
    if 'TM08' in rules:
        return 'RFI_COUNTERPARTY_DETAILS'
    if 'TM04' in rules or 'TM02' in rules or 'TM10' in rules:
        if biz:
            return 'RFI_BUSINESS_RECORDS'
        return 'RFI_PURPOSE_DOCUMENTS'
    if outs and not ins:
        return 'RFI_PURPOSE_DOCUMENTS'
    return 'RFI_BUSINESS_RECORDS' if biz else 'RFI_SOURCE_OF_FUNDS'


def collection_like(ins):
    """Payments from several people that share a common purpose word (a trip, a collection)."""
    if len(ins) < 3:
        return False
    words = {}
    for t in ins:
        for w in set(norm(t.get('reference')).split()):
            if len(w) > 3 and w not in ('payment', 'transfer', 'thanks', 'from'):
                words[w] = words.get(w, 0) + 1
    amts = {}
    for t in ins:
        amts[round(t['amount_gbp'], 2)] = amts.get(round(t['amount_gbp'], 2), 0) + 1
    if max(amts.values()) >= 0.6 * len(ins):
        return True
    return any(n >= 0.6 * len(ins) for n in words.values())


CLAIMS = [('sale of a car or vehicle', r'sell(?:ing)? my (?:car|motorbike|bike|van|vehicle)|car sale'),
          ('gift from a relative', r'gift from|present from'),
          ('loan from a friend', r'loan from'),
          ('family support', r'family support|help my family'),
          ('savings kept at home', r'savings|kept it at home|keeping it at home')]


def structural_flags(case_docs, cust, txs, data):
    """Suspicion that comes from the documents taken together."""
    flags = []
    # a counterparty that the register shows was dissolved before it paid
    for d in case_docs:
        if d.type != 'company_register_extract':
            continue
        m = re.search(r'Dissolved(?: on)?:?\s+([0-9]{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\.?,?\s+\d{4}|[A-Za-z]+\.?\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})', d.text, re.I)
        comp = d.field('Company') or ''
        if m and comp:
            dd = parse_date(m.group(1))
            hits = [t for t in txs if name_key(t.get('counterparty_name')) == name_key(comp) and (not dd or (tx_date(t) and tx_date(t) > dd))]
            if hits:
                flags.append(('ESC_UNEXPLAINED_FUNDS', [d.id] + [t['transaction_id'] for t in hits[:3]],
                              '%s shows %s was dissolved on %s, yet %s in its name moved through the account' % (
                                  d.id, comp, dd.strftime('%-d %B %Y') if dd else m.group(1), money(sum(t['amount_gbp'] for t in hits)))))
    # newly formed companies controlled by the customer's own director, with no group structure on file
    own = [d for d in case_docs if d.type == 'company_register_extract' and name_key(d.field('Company') or '') == name_key(cust.get('name'))]
    people = set()
    for d in own:
        for r in register_rows(d):
            p = r.get('officer') or r.get('person with significant control') or r.get('person') or ''
            if p:
                people.add(name_key(p))
    if cust.get('kind') == 'individual':
        people.add(name_key(cust.get('name')))
    if not any(d.type == 'group_structure' for d in case_docs):
        linked = []
        for d in case_docs:
            if d.type != 'company_register_extract' or d in own or re.search(r'Dissolved', d.text, re.I):
                continue
            ppl = {name_key(r.get('officer') or r.get('person with significant control') or r.get('person') or '') for r in register_rows(d)}
            inc = parse_date(d.field('Incorporated') or '')
            if ppl & people and inc and d.dated and (d.dated - inc).days < 400:
                linked.append(d)
        if linked:
            flags.append(('ESC_PASS_THROUGH', [d.id for d in linked],
                          'money passes through to newly formed companies controlled by the same person (%s)' % ', '.join(
                              '%s, incorporated %s, %s' % (d.field('Company'), d.field('Incorporated'), d.id) for d in linked[:2])))
    # the customer gives different explanations for the same money
    chats = [d for d in case_docs if d.type in ('support_chat', 'staff_note', 'contact_note')]
    claims = []
    for d in chats:
        for label, pat in CLAIMS:
            if re.search(pat, d.low):
                claims.append((label, d))
    labels = sorted(set(c[0] for c in claims))
    docs_with = sorted(set(c[1].id for c in claims))
    if len(labels) >= 2 and len(docs_with) >= 2:
        flags.append(('ESC_UNEXPLAINED_FUNDS', docs_with, 'the customer gave inconsistent explanations (%s) in %s' % (' and '.join(labels), ', '.join(docs_with))))
    return flags


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
            txt = lead[0][2]
            if txt and not re.match(r'[A-Z]{2,}|[A-Z][a-z]+ [A-Z]', txt):
                txt = txt[0].lower() + txt[1:]
            sents.append('%s: %s.' % (cname, txt))
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
        shape = describe_shape(code, unexplained, cust)
        if shape:
            sents.insert(1 if lead else 0, shape)
        sents.append('That is a sign of %s, so the case goes to the MLRO and the customer is not asked (tipping-off risk).' % ESC_WORDS.get(code, 'suspicious activity'))
    elif verdict == 'RFI':
        lead = [i for i in main_items if i[2]]
        if lead:
            sents.append('%s: %s.' % (cname, lead[0][2]))
            ev += lead[0][1]
        if unexplained:
            tot = sum(t['amount_gbp'] for t in unexplained)
            sents.append('%s (%s) %s driven by %s totalling %s that no document on file explains (%s).' % (
                ('The alerts' if sents else cname + ': the alerts'), rule_txt, 'are', 'one transaction' if len(unexplained) == 1 else '%d transactions' % len(unexplained), money(tot),
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
            sents.append(routine_summary(routine))
        sents.append('Every alert in the case (%s) is explained by the evidence, so the case is closed as %s.' % (rule_txt, code))
    if verdict != 'CLOSE':
        for c in items:
            ev += c[1]
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



# ---------------------------------------------------------------- extra checks (v2)
CATEGORIES = [
    ('services', r'consult|advisory|market access|services|management fee|software|developer|marketing'),
    ('phones', r'mobile phone|handset|smartphone|iphone'),
    ('electronics', r'electronic|laptop|semiconductor|chip\b|circuit|component'),
    ('food', r'food|drink|fruit|vegetable|produce|apricot|fig|dates\b|wine|spirit|coffee|tea\b|grocer|restaurant'),
    ('furniture', r'furniture|sofa|chair|table|wardrobe|hotel'),
    ('timber', r'timber|wood|lumber|building material|plywood'),
    ('clothing', r'clothing|apparel|garment|textile|fabric|fashion'),
    ('machinery', r'machine|machinery|engineering|parts|equipment|tools?\b'),
    ('catering', r'catering|oven|fridge|kitchen'),
    ('freight', r'freight|shipping|carrier|haulage|logistics|forwarding'),
]


def categories(text):
    t = (text or '').lower()
    return {c for c, p in CATEGORIES if re.search(p, t)}


def goods_text(d):
    g = d.field('Goods') or d.field('Description') or d.field('Scope') or ''
    if not g:
        rows = register_rows(d)
        g = ' '.join(r.get('goods', '') or r.get('description', '') for r in rows)
    return g


def goods_mismatch(d, cust):
    if cust.get('kind') != 'business':
        return None
    g = goods_text(d)
    gc = categories(g)
    bc = categories(cust.get('business_activity'))
    if 'catering' in bc:
        bc |= {'machinery'}
    if 'machinery' in bc:
        bc |= {'catering'}
    if gc and bc and not (gc & bc):
        return '%s bills %s, which does not fit %s\'s business (%s)' % (d.id, g.strip().rstrip('.')[:80], cust.get('name'), cust.get('business_activity'))
    return None


def group_link(t, cust, docs):
    cp = t.get('counterparty_name') or ''
    if not cp:
        return None
    for d in docs:
        if d.type != 'group_structure':
            continue
        if not (name_in(cp, d.norm) and name_in(cust.get('name') or '', d.norm)):
            continue
        rows = register_rows(d)
        owner = {}
        for r in rows:
            comp = r.get('company') or ''
            own = r.get('owned by') or r.get('owner') or r.get('parent') or ''
            owner[name_key(comp)] = name_key(own)

        def chain(x):
            seen = [x]
            while x in owner and owner[x] not in seen:
                x = owner[x]
                seen.append(x)
            return seen
        a, b = chain(name_key(cust.get('name'))), chain(name_key(cp))
        if set(a[1:] + a[:1]) & set(b) and (set(a[1:]) & set(b) or name_key(cp) in a or name_key(cust.get('name')) in b):
            return d
    return None


def payment_file_flags(docs):
    out = []
    for d in docs:
        if d.type != 'payment_file':
            continue
        rows = register_rows(d)
        addr = {}
        for r in rows:
            a = norm(r.get('address'))
            p = r.get('payee') or r.get('contractor') or r.get('name') or ''
            if a:
                addr.setdefault(a, set()).add(p)
        shared = sorted((a, sorted(ps)) for a, ps in addr.items() if len(ps) > 1)
        if shared:
            out.append(('ESC_MULE_ACTIVITY', d, 'payment file %s pays %d different people at the same %d addresses (e.g. %s at %s)' % (
                d.id, sum(len(p) for a, p in shared), len(shared), ', '.join(shared[0][1][:3]), shared[0][0].title())))
    return out


def own_funding(t, cust, docs, data):
    """Money in from an account in the customer's own name: shown by a statement in their name
    (the onward leg to their own account), or by supplier invoices / orders it was raised to pay."""
    td = tx_date(t)
    mine = [d for d in docs if d.type == 'bank_statement' and name_key(d.field('Account holder') or '') == name_key(cust.get('name'))]
    outs = [o for o in data.tx_by_cust.get(cust.get('customer_id'), []) if o['direction'] == 'out' and
            name_key(o.get('counterparty_name')) == name_key(cust.get('name'))]
    for d in mine:
        for o in outs:
            if d.has_amount(o['amount_gbp']) or (o.get('amount') and d.has_amount(o['amount'])) or \
                    (len(digits(o.get('counterparty_account'))) >= 4 and digits(o.get('counterparty_account'))[-4:] in d.digits):
                return {'code': 'OWN_ACCOUNT', 'docs': [d], 'extra': [o['transaction_id']],
                        'note': '%s funding from %s\'s own bank, paid on to its own account at %s (%s, %s)' % (
                            money(t['amount_gbp']), cust.get('name'), d.field('Bank') or 'another bank', d.id, o['transaction_id'])}
    invs = [d for d in docs if d.type in ('supplier_invoice', 'supplier_invoices', 'purchase_order') and not goods_mismatch(d, cust)]
    sup = [d for d in invs if d.type != 'purchase_order']
    if sup and td:
        for d in sup:
            if d.dated and -31 <= (d.dated - td).days <= 3 and d.amounts and max(d.amounts) <= t['amount_gbp'] * 1.05 and \
                    max(d.amounts) >= 0.5 * t['amount_gbp']:
                po = [x for x in invs if x.type == 'purchase_order']
                return {'code': 'INVOICE_MATCHES', 'docs': [d] + po[:1],
                        'note': '%s own funding on %s covers supplier invoice %s for %s (%s)%s' % (
                            money(t['amount_gbp']), td.isoformat(), d.id, goods_text(d).strip()[:60] or 'goods', money(max(d.amounts)),
                            (', raised for customer order %s' % po[0].id) if po else '')}
    return None


def established_payee(t, cust, data, case):
    """A payee the customer has paid repeatedly before the review window, in a declared country."""
    start = (case.get('review_window') or {}).get('from') or (t.get('booked_at') or '')[:10]
    prior = [o for o in data.tx_by_cust.get(cust.get('customer_id'), []) if o['direction'] == 'out' and
             o.get('counterparty_name') == t.get('counterparty_name') and (o.get('booked_at') or '')[:10] < start]
    exp = {norm(c) for c in ((cust.get('declared') or {}).get('expected_countries') or [])}
    if len(prior) >= 2 and (not t.get('counterparty_country') or norm(t.get('counterparty_country')) in exp):
        return {'code': 'WITHIN_PROFILE', 'docs': [], 'routine': True, 'extra': [prior[-1]['transaction_id']],
                'note': '%s is an established payee in %s, paid %d times before the review window (last %s)' % (
                    t.get('counterparty_name'), t.get('counterparty_country') or 'the UK', len(prior), prior[-1]['booked_at'][:10])}
    return None


ESC_WORDS = {'ESC_MULE_ACTIVITY': 'money-mule activity', 'ESC_STRUCTURING': 'structuring below a threshold',
             'ESC_UNEXPLAINED_FUNDS': 'funds with no credible explanation being moved on', 'ESC_PASS_THROUGH': 'pass-through to linked parties',
             'ESC_INVOICE_MISMATCH': 'invoices that do not support the payments', 'ESC_HIGH_RISK_CORRIDOR': 'unexplained higher-risk corridor activity',
             'ESC_ACCOUNT_MISUSE': 'someone other than the customer using the account', 'ESC_THIRD_PARTY_FUNDING': 'unrelated third-party funding',
             'ESC_EARLY_REDEMPTION': 'early redemption used to move money', 'ESC_LISTED_PARTY': 'dealing with a party on the internal list'}


def routine_summary(routine):
    kinds = _uniq([e['note'].split(' such as ')[0] if ' such as ' in e['note'] else e['note'] for (t, e) in routine])
    small = [t for (t, e) in routine if 'minor next to' in e['note']]
    parts = [k for k in kinds if not k.startswith('small everyday')][:2]
    if small:
        parts.append('%d smaller own-name or everyday transfer%s (largest %s)' % (len(small), '' if len(small) == 1 else 's', money(max(t['amount_gbp'] for t in small))))
    return 'The rest of the alerted activity is ordinary: %s.' % '; '.join(parts)


def describe_shape(code, unexplained, cust):
    ins = [t for t in unexplained if t['direction'] == 'in']
    outs = [t for t in unexplained if t['direction'] == 'out']
    payers = _uniq([t.get('counterparty_name') for t in ins if name_key(t.get('counterparty_name')) != name_key(cust.get('name'))])
    payees = _uniq([t.get('counterparty_name') for t in outs])
    ctry = _uniq([t.get('counterparty_country') for t in outs if t.get('counterparty_country') and norm(t.get('counterparty_country')) != 'united kingdom'])
    if code in ('ESC_HIGH_RISK_CORRIDOR', 'ESC_MULE_ACTIVITY', 'ESC_THIRD_PARTY_FUNDING', 'ESC_PASS_THROUGH', 'ESC_UNEXPLAINED_FUNDS') and payers and outs:
        return '%s from %d unrelated payer%s (%s) was paid straight out to %s%s.' % (
            money(sum(t['amount_gbp'] for t in ins)), len(payers), '' if len(payers) == 1 else 's', ', '.join(payers[:3]),
            ', '.join(payees[:3]) + (' and %d others' % (len(payees) - 3) if len(payees) > 3 else ''),
            (' in ' + ', '.join(ctry)) if ctry else '')
    return ''


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write('usage: run <institution folder> <output file>\n')
        sys.exit(2)
    tp = os.environ.get('TM_TRACE')
    run(sys.argv[1], sys.argv[2], tp)
