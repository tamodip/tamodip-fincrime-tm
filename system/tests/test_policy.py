#!/usr/bin/env python3
"""Unit tests for the policy-facing building blocks of tm.py (stdlib unittest)."""
import datetime as dt, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tm  # noqa: E402


class P:
    def __init__(self, text):
        self.policy = text


def fixture(name):
    with open(os.path.join(HERE, 'fixtures', name), encoding='utf-8') as fh:
        return fh.read()


class TestVerdictCodes(unittest.TestCase):
    def test_every_code_maps_to_its_family(self):
        for code, verdict in tm.VERDICT_OF.items():
            want = 'ESCALATE' if code.startswith('ESC_') else 'RFI' if code.startswith('RFI_') else 'CLOSE'
            self.assertEqual(verdict, want, code)

    def test_code_set_is_complete(self):
        self.assertEqual(len(tm.VERDICT_OF), 26)
        self.assertEqual(sum(v == 'CLOSE' for v in tm.VERDICT_OF.values()), 11)
        self.assertEqual(sum(v == 'RFI' for v in tm.VERDICT_OF.values()), 5)
        self.assertEqual(sum(v == 'ESCALATE' for v in tm.VERDICT_OF.values()), 10)

    def test_escalation_priority_only_uses_esc_codes(self):
        for c in tm.ESC_PRIORITY:
            self.assertEqual(tm.VERDICT_OF[c], 'ESCALATE')
        self.assertEqual(tm.ESC_PRIORITY[0], 'ESC_LISTED_PARTY')


class TestPolicySettings(unittest.TestCase):
    def test_bank_policy(self):
        s = tm.policy_settings(P(fixture('POLICY_bank.md')))
        self.assertEqual(s['own_rfi_multiple'], 5.0)
        self.assertIsNone(s['invoice_threshold'])
        self.assertIn('TM05', s['rules_run'])
        self.assertNotIn('TM10', s['rules_run'])

    def test_payments_fx_policy(self):
        s = tm.policy_settings(P(fixture('POLICY_payments_fx.md')))
        self.assertEqual(s['invoice_threshold'], 10000.0)
        self.assertIn('TM08', s['rules_run'])
        self.assertNotIn('TM05', s['rules_run'])

    def test_changed_numbers_are_read_not_hardcoded(self):
        txt = fixture('POLICY_payments_fx.md').replace('£10,000 or more to anyone other than the client', '£25,000 or more to anyone other than the client')
        txt = txt.replace('own accounts explain activity at 5 times', 'own accounts explain activity at 8 times')
        s = tm.policy_settings(P(txt))
        self.assertEqual(s['invoice_threshold'], 25000.0)
        if 'own accounts explain activity at' in fixture('POLICY_payments_fx.md'):
            self.assertEqual(s['own_rfi_multiple'], 8.0)

    def test_missing_policy_falls_back_to_defaults(self):
        s = tm.policy_settings(P(''))
        self.assertEqual(s['own_rfi_multiple'], 5.0)
        self.assertIsNone(s['invoice_threshold'])


class TestParsing(unittest.TestCase):
    def test_dates(self):
        d = dt.date(2026, 3, 5)
        for s in ['2026-03-05', '5 March 2026', 'March 5, 2026', '05/03/2026', '5th March 2026']:
            self.assertEqual(tm.parse_date(s), d, s)

    def test_bad_dates(self):
        for s in ['', None, 'soon', '31/31/2026']:
            self.assertIsNone(tm.parse_date(s), s)

    def test_amounts(self):
        self.assertIn(13000.0, tm.amounts_in('Sale price: £13,000.00 paid in cash'))
        self.assertIn(13000.0, tm.amounts_in('GBP 13,000.00'))
        self.assertIn(994838.33, tm.amounts_in('Total due £994,838.33'))
        self.assertIn(250.5, tm.amounts_in('fee 250.50 GBP'))

    def test_money_format(self):
        self.assertEqual(tm.money(1234.5), '£1,234.50')

    def test_name_matching_ignores_suffixes_and_punctuation(self):
        txt = tm.norm('Payment to STANFORD CONSULTING LIMITED, invoice 12')
        self.assertTrue(tm.name_in('Stanford Consulting Ltd', txt))
        self.assertFalse(tm.name_in('Stanford Holdings Ltd', txt))
        self.assertFalse(tm.name_in('Ltd', txt))

    def test_name_match_is_whole_word(self):
        self.assertFalse(tm.name_in('Ann Lee', tm.norm('Joann Leeds')))


class TestRedFlagWording(unittest.TestCase):
    def flags(self, text):
        hits = []
        for rx, code, label in tm.RED_FLAGS:
            if __import__('re').search(rx, text, __import__('re').I):
                hits.append(code)
        return hits

    def test_structuring_wording(self):
        for t in ['Can we split it so each payment stays under £10,000?', 'Please keep each deposit below the limit',
                  'He asked to pay in instalments of less than £9,000', 'They wanted to avoid the reporting threshold']:
            self.assertIn('ESC_STRUCTURING', self.flags(t), t)

    def test_mule_wording(self):
        self.assertIn('ESC_MULE_ACTIVITY', self.flags('My manager said I keep 10% and send the rest on'))

    def test_account_misuse_wording(self):
        self.assertIn('ESC_ACCOUNT_MISUSE', self.flags('I gave my login to a friend who let them use it'))

    def test_innocent_text_has_no_flags(self):
        self.assertEqual(self.flags('Invoice for consultancy services rendered in July. Payment terms 30 days.'), [])


if __name__ == '__main__':
    unittest.main(verbosity=1)
