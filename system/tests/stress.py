#!/usr/bin/env python3
"""Paraphrase / format stress harness.

Copies an institution folder, rewrites it the way unseen cases might differ (date formats, amount
formats, casing, markdown labels, synonyms, file order), reruns the system and compares verdicts.
A verdict may stay the same or move to a safer one (CLOSE -> RFI/ESCALATE, RFI -> ESCALATE);
moving towards CLOSE is a failure.
"""
import json, os, random, re, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.dirname(HERE)
RANK = {'CLOSE': 0, 'RFI': 1, 'ESCALATE': 2}
MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October',
          'November', 'December']


def iso_to_words(m):
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return '%d %s %d' % (d, MONTHS[mo - 1], y)


def words_to_us(m):
    return '%s %d, %s' % (m.group(2), int(m.group(1)), m.group(3))


def words_to_slash(m):
    return '%02d/%02d/%s' % (int(m.group(1)), MONTHS.index(m.group(2)) + 1, m.group(3))


VARIANTS = {
    'dates_us': lambda t: re.sub(r'\b(\d{1,2}) (%s) (\d{4})\b' % '|'.join(MONTHS), words_to_us, t),
    'dates_slash': lambda t: re.sub(r'\b(\d{1,2}) (%s) (\d{4})\b' % '|'.join(MONTHS), words_to_slash, t),
    'amount_gbp_code': lambda t: re.sub(r'£(\d{1,3}(?:,\d{3})*\.\d{2})', lambda m: 'GBP ' + m.group(1).replace(',', ''), t),
    'amount_space': lambda t: re.sub(r'£(\d)', r'£ \1', t),
    'plain_labels': lambda t: re.sub(r'\*\*([A-Za-z ]+):\*\*', r'\1:', t),
    'upper_case': lambda t: t.upper(),
    'lower_case': lambda t: t.lower(),
    'synonyms': lambda t: (t.replace('born ', 'date of birth ').replace('Dear ', 'Hello ').replace('confirm', 'certify')
                           .replace('we have processed', 'we have now completed').replace('Kind regards', 'Best wishes')),
}


def perturb(src, dst, variant, seed=7):
    shutil.copytree(src, dst)
    rnd = random.Random(seed)
    fn = VARIANTS.get(variant)
    if fn:
        ev = os.path.join(dst, 'evidence')
        for name in sorted(os.listdir(ev)):
            p = os.path.join(ev, name)
            text = open(p, encoding='utf-8').read()
            head, _, body = text.partition('\n')
            # keep the Markdown title line and the Document ID line intact, rewrite the rest
            open(p, 'w', encoding='utf-8').write(head + '\n' + fn(body).replace('DOCUMENT ID', 'Document ID').replace('document id', 'Document ID'))
    if variant == 'shuffle':
        for name in sorted(os.listdir(dst)):
            if name.endswith('.jsonl') and name != 'cases.jsonl':
                p = os.path.join(dst, name)
                lines = open(p, encoding='utf-8').read().splitlines()
                rnd.shuffle(lines)
                open(p, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def run(folder, out):
    subprocess.check_call([os.path.join(SYSTEM, 'run'), folder, out])
    return {r['case_id']: r for r in map(json.loads, open(out, encoding='utf-8'))}


def main(folder, variants=None, limit=None):
    variants = variants or ['shuffle'] + sorted(VARIANTS)
    tmp = tempfile.mkdtemp(prefix='tmstress_')
    base = run(folder, os.path.join(tmp, 'base.jsonl'))
    total_bad = 0
    print('variant            same  safer  UNSAFE')
    for v in variants:
        d = os.path.join(tmp, v, os.path.basename(os.path.normpath(folder)))
        perturb(folder, d, v)
        got = run(d, os.path.join(tmp, v + '.jsonl'))
        same = safer = unsafe = 0
        bad = []
        for cid, r in base.items():
            g = got[cid]
            if g['verdict'] == r['verdict']:
                same += 1
            elif RANK[g['verdict']] > RANK[r['verdict']]:
                safer += 1
            else:
                unsafe += 1
                bad.append((cid, r['verdict'], g['verdict']))
        total_bad += unsafe
        print('%-18s %5d %6d %7d' % (v, same, safer, unsafe))
        for b in bad[:3]:
            print('    unsafe:', b)
    shutil.rmtree(tmp, ignore_errors=True)
    return total_bad


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1], sys.argv[2:] or None) else 0)
