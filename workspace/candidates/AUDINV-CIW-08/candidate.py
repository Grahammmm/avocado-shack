#!/usr/bin/env python3
"""AUDINV-CIW-08 offline merges-per-pass evidence checker. Local-only, stdlib, read-only.

  --self-test                          run the named synthetic checks (embedded unittest cases)
  --check REPORT.md --sources SRC.json validate the report against its sources (paths beneath this directory)

No network, no subprocess, no writes. Missing evidence is UNKNOWN (None), never zero."""
import argparse, datetime as dt, hashlib, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.realpath(__file__))
SCHEMA = 1
UTC = dt.timezone.utc
LOCAL_TZ = dt.timezone(dt.timedelta(hours=-8))  # ship.log writes host-local time (PST on 2026-11-13..14)
MERGE_RE = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) (\S+) MERGED ([\w.-]+/[\w.-]+)#(\d+) at ([0-9a-f]{40})(?: \(CI2-A group position (\d+)\))?\s*$')
TS_RE = re.compile(r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d$')
OPEN_LOG = []  # every file open attempted through _open (side-effect boundary test)


class Bad(ValueError):
    pass


def _open(path, mode='r'):
    OPEN_LOG.append((path, mode))
    return open(path, mode, encoding='utf-8')


def safe_path(name, root=ROOT):
    """Resolve name beneath root; reject absolute, traversal, symlinks, anything outside. Opens nothing."""
    if not isinstance(name, str) or not name or os.path.isabs(name) or '\x00' in name:
        raise Bad('path not allowed: %r' % (name,))
    if '..' in name.split('/'):
        raise Bad('path traversal: %r' % (name,))
    cur = os.path.realpath(root)
    for part in name.split('/'):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            raise Bad('symlink not allowed: %r' % (name,))
    if os.path.commonpath([os.path.realpath(root), os.path.realpath(cur)]) != os.path.realpath(root):
        raise Bad('outside package root: %r' % (name,))
    return cur


def load_json(name, root=ROOT):
    with _open(safe_path(name, root)) as f:
        text = f.read()
    return parse_json(text)


def parse_json(text):
    def pairs(items):
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise Bad('duplicate key in JSON object')
        return dict(items)
    try:
        data = json.loads(text, object_pairs_hook=pairs)
    except json.JSONDecodeError as e:
        raise Bad('malformed JSON: %s' % e)
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA:
        raise Bad('unknown or missing schema_version (want %d)' % SCHEMA)
    return data


def utc(s):
    if not isinstance(s, str) or not re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ', s):
        raise Bad('bad UTC timestamp: %r' % (s,))
    return dt.datetime.strptime(s, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=UTC)


def parse_receipt(line):
    """ship.log MERGED receipt line -> merge dict (UTC time derived with the stated local-tz assumption)."""
    m = MERGE_RE.match(line)
    if not m:
        raise Bad('not a MERGED receipt: %r' % line[:80])
    t = dt.datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S').replace(tzinfo=LOCAL_TZ).astimezone(UTC)
    return {'repo': m.group(3), 'pr': int(m.group(4)), 'head': m.group(5), 'ts': t.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'row_id': m.group(2), 'group_position': int(m.group(6)) if m.group(6) else None}


def lines_digest(lines):
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


def analyze(d):
    """Pure measurement from a v1 source document. Returns the machine summary dict."""
    for k in ('repo', 'window_start', 'window_end', 'pass_enumeration', 'passes', 'merges'):
        if k not in d:
            raise Bad('missing key %s' % k)
    if d['pass_enumeration'] not in ('complete', 'incomplete', 'none'):
        raise Bad('bad pass_enumeration')
    lo, hi, repo = utc(d['window_start']), utc(d['window_end']), d['repo']
    if not lo < hi:
        raise Bad('empty window')
    # passes keyed by (pass_id, repo, ts); a missing id or incomplete enumeration makes the denominator UNKNOWN
    pass_ids, missing_id, dup_pass = set(), 0, 0
    for p in d['passes']:
        if p.get('repo') != repo or not (lo <= utc(p.get('ts')) < hi):
            continue
        pid = p.get('pass_id')
        if not pid:
            missing_id += 1
        elif pid in pass_ids:
            dup_pass += 1
        else:
            pass_ids.add(pid)
    denom_ok = d['pass_enumeration'] == 'complete' and missing_id == 0 and dup_pass == 0 and bool(d['passes'])
    # merges keyed by (pr, head); window start inclusive, end exclusive, other repos excluded
    heads, excluded_repo, outside = {}, 0, 0
    for m in d['merges']:
        if m.get('repo') != repo:
            excluded_repo += 1
            continue
        if not (lo <= utc(m.get('ts')) < hi):
            outside += 1
            continue
        if not re.fullmatch(r'[0-9a-f]{40}', str(m.get('head'))) or not isinstance(m.get('pr'), int):
            raise Bad('merge needs integer pr and full 40-hex head')
        h = heads.setdefault(m['pr'], {})
        h.setdefault(m['head'], m.get('pass_id'))
    conflict_prs = sorted(pr for pr, h in heads.items() if len(h) > 1)
    unique = sorted((pr, head, pid) for pr, h in heads.items() if pr not in conflict_prs for head, pid in h.items())
    linked = [u for u in unique if u[2] in pass_ids]  # explicit pass link only, never timestamp proximity
    unlinked = [u for u in unique if u[2] not in pass_ids]
    denom = len(pass_ids) if denom_ok else None
    numerator = len(linked) if not unlinked and not conflict_prs else None
    ratio = numerator / denom if numerator is not None and denom else None
    return {
        'schema_version': SCHEMA, 'repo': repo, 'window': [d['window_start'], d['window_end']],
        'passes_recorded': len(pass_ids), 'passes_missing_id': missing_id,
        'pass_enumeration': d['pass_enumeration'],
        'denominator': denom,
        'unique_merges_in_window': len(unique),
        'numerator': numerator,
        'ratio': ratio,
        'overall_status': 'KNOWN' if ratio is not None else 'UNKNOWN',
        'unlinked_merges': [{'pr': p, 'head': h} for p, h, _ in unlinked],
        'conflicting_head_prs': conflict_prs,
        'excluded_other_repo': excluded_repo, 'excluded_outside_window': outside,
    }


def check_sources(d):
    """Bind each receipt line to its structured fields and the recorded digest."""
    lines = d.get('receipt_lines')
    if not isinstance(lines, list) or d.get('receipt_lines_sha256') != lines_digest(lines):
        raise Bad('receipt_lines digest mismatch')
    parsed = [parse_receipt(l) for l in lines]
    fields = ('repo', 'pr', 'head', 'ts', 'row_id', 'group_position')
    got = sorted(json.dumps([p[k] for k in fields]) for p in parsed)
    want = sorted(json.dumps([m.get(k) for k in fields]) for m in d['merges'])
    if got != want:
        raise Bad('merges do not match their receipt lines')
    if not d.get('missing_coverage'):
        raise Bad('missing_coverage must be stated')


def report_block(text):
    m = re.search(r'<!-- MACHINE-SUMMARY -->\s*```json\n(.*?)\n```', text, re.S)
    if not m:
        raise Bad('no MACHINE-SUMMARY json block')
    return parse_json(m.group(1))


def check_report(report_text, sources):
    check_sources(sources)
    want = analyze(sources)
    got = report_block(report_text)
    if got != want:
        raise Bad('report summary differs from recomputed source summary')
    # Validate displayed claims too, not just the machine block. Ignore fenced
    # historical command receipts; normalize the report's bullets/bold/code spans.
    prose = re.sub(r'^```[^\n]*\n.*?^```\s*$', '', report_text, flags=re.M | re.S)
    labels = {'ratio': 'ratio', 'merges per pass': 'ratio', 'denominator': 'denominator',
              'numerator': 'numerator', 'verified unique merges in window': 'unique_merges_in_window'}
    for line in prose.splitlines():
        plain = re.sub(r'[*`_]', '', line)
        plain = re.sub(r'^\s*(?:[-+>]\s+|#{1,6}\s+)*', '', plain)
        claim = re.match(r'(ratio|merges per pass|denominator|numerator|verified unique merges in window)'
                         r'(?:\s*\([^\n:]*\))?\s*[:=]\s*(.*)', plain, re.I)
        if not claim:
            continue
        value = re.match(r'(UNKNOWN|[+-]?\d+(?:\.\d+)?)(?=$|[\s.,;)])', claim[2], re.I)
        if not value:
            raise Bad('unrecognized presented result: %s' % claim[0])
        actual = None if value[1].upper() == 'UNKNOWN' else float(value[1])
        if actual != want[labels[claim[1].lower()]]:
            raise Bad('presented result differs from source summary: %s' % claim[0])
    return want


def cmd_check(report, sources):
    text = _open(safe_path(report)).read()
    s = load_json(sources)
    w = check_report(text, s)
    print('CHECK OK: %s merges=%d numerator=%s denominator=%s ratio=%s status=%s' % (
        w['repo'], w['unique_merges_in_window'], 'UNKNOWN' if w['numerator'] is None else w['numerator'],
        'UNKNOWN' if w['denominator'] is None else w['denominator'],
        'UNKNOWN' if w['ratio'] is None else w['ratio'], w['overall_status']))


# ---------------------------------------------------------------- embedded tests (local-only, named in README)
H = lambda c: c * 40
BASE = {'schema_version': 1, 'repo': 'o/r', 'window_start': '2026-11-14T00:00:00Z', 'window_end': '2026-11-15T00:00:00Z',
        'pass_enumeration': 'complete', 'passes': [], 'merges': []}


def doc(**kw):
    d = json.loads(json.dumps(BASE))
    d.update(kw)
    return d


def mg(pr, head, ts='2026-11-14T12:00:00Z', pid=None, repo='o/r'):
    return {'repo': repo, 'pr': pr, 'head': head, 'ts': ts, 'pass_id': pid}


def ps(pid, ts='2026-11-14T12:00:00Z', repo='o/r'):
    return {'pass_id': pid, 'repo': repo, 'ts': ts}


class Cases(unittest.TestCase):
    fixtures = None

    def test_explicit_two_passes_include_zero_merge_denominator(self):
        r = analyze(doc(passes=[ps('p1'), ps('p2')], merges=[mg(1, H('a'), pid='p1')]))
        self.assertEqual((r['numerator'], r['denominator'], r['ratio']), (1, 2, 0.5))
        self.assertEqual(r['overall_status'], 'KNOWN')

    def test_duplicate_receipt_same_head_counted_once(self):
        r = analyze(doc(passes=[ps('p1')], merges=[mg(1, H('a'), pid='p1'), mg(1, H('a'), pid='p1')]))
        self.assertEqual((r['unique_merges_in_window'], r['numerator'], r['ratio']), (1, 1, 1.0))

    def test_missing_pass_id_or_capped_export_keeps_overall_ratio_unknown(self):
        for kw in (dict(passes=[ps('p1'), {'repo': 'o/r', 'ts': '2026-11-14T13:00:00Z'}]),
                   dict(passes=[ps('p1')], pass_enumeration='incomplete'),
                   dict(passes=[], pass_enumeration='none')):
            r = analyze(doc(merges=[mg(1, H('a'), pid='p1')], **kw))
            self.assertIsNone(r['denominator']); self.assertIsNone(r['ratio'])
            self.assertEqual(r['overall_status'], 'UNKNOWN')

    def test_conflicting_head_and_unlinked_merge_not_silently_joined(self):
        r = analyze(doc(passes=[ps('p1', '2026-11-14T12:00:05Z')],
                        merges=[mg(1, H('a'), pid='p1'), mg(1, H('b'), pid='p1'), mg(2, H('c'), '2026-11-14T12:00:06Z')]))
        self.assertEqual(r['conflicting_head_prs'], [1])
        self.assertIsNone(r['numerator'])  # conflict and near-in-time PR 2 remain unresolved
        self.assertEqual(r['unlinked_merges'], [{'pr': 2, 'head': H('c')}])

    def test_unresolved_numerator_keeps_ratio_unknown_with_complete_passes(self):
        for merges in ([mg(1, H('a'))],
                       [mg(1, H('a'), pid='p1'), mg(1, H('b'), pid='p1')],
                       [mg(1, H('a'), pid='p1'), mg(2, H('b'))]):
            with self.subTest(merges=merges):
                r = analyze(doc(passes=[ps('p1')], merges=merges))
                self.assertEqual(r['denominator'], 1)
                self.assertIsNone(r['numerator'])
                self.assertIsNone(r['ratio'])
                self.assertEqual(r['overall_status'], 'UNKNOWN')
        r = analyze(doc(passes=[ps('p1')]))
        self.assertEqual((r['numerator'], r['ratio'], r['overall_status']), (0, 0.0, 'KNOWN'))

    def test_window_start_inclusive_end_exclusive_and_other_repo_excluded(self):
        ms = [mg(1, H('a'), '2026-11-14T00:00:00Z'), mg(2, H('b'), '2026-11-15T00:00:00Z'),
              mg(3, H('c'), '2026-11-13T23:59:59Z'), mg(4, H('d'), '2026-11-14T05:00:00Z', repo='o/other')]
        r = analyze(doc(passes=[ps('p1')], merges=ms))
        self.assertEqual([m['pr'] for m in r['unlinked_merges']], [1])
        self.assertEqual((r['excluded_outside_window'], r['excluded_other_repo']), (2, 1))

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        OPEN_LOG.clear()
        for bad in ('../x.json', '/etc/passwd', 'a/../../x', '', 'sub/\x00'):
            with self.assertRaises(Bad):
                safe_path(bad)
        link = os.path.join(ROOT, '.selftest-link')
        os.symlink('/etc', link)  # task-local, removed below
        try:
            with self.assertRaises(Bad):
                safe_path('.selftest-link/passwd')
        finally:
            os.unlink(link)
        for text in ('{"schema_version": 2}', '{"schema_version": 1, "a": 1, "a": 2}', '[1]', '{bad'):
            with self.assertRaises(Bad):
                parse_json(text)
        with self.assertRaises(Bad):
            analyze(doc(merges=[mg(1, 'abc')]))
        with self.assertRaises(Bad):
            analyze(doc(window_end='2026-11-13T00:00:00Z'))
        self.assertEqual(OPEN_LOG, [])  # rejection happened before anything was opened

    def test_fixtures_file_expected_outcomes(self):
        fx = load_json('fixtures.json')
        for case in fx['cases']:
            r = analyze(dict(fx['base'], pass_enumeration=case['pass_enumeration'], passes=case['passes'], merges=case['merges']))
            for k, v in case['expect'].items():
                self.assertEqual(r[k], v, '%s: %s' % (case['name'], k))

    def test_presented_markdown_results_match_source_summary(self):
        src = load_json('SOURCES.json')
        with _open(safe_path('avocado-merges-per-pass-20261114.md')) as f:
            report = f.read()
        check_report(report, src)
        for old, new in (('**Merges per pass: UNKNOWN**', '**Merges per pass: 99**'),
                         ('(passes): UNKNOWN.', '(passes): 99.'),
                         ('recorded pass): UNKNOWN', 'recorded pass): 99'),
                         (': **34**, all reported', ': **99**, all reported')):
            with self.subTest(claim=old):
                self.assertIn(old, report)
                with self.assertRaises(Bad):
                    check_report(report.replace(old, new), src)
        known = json.loads(json.dumps(src))
        known['passes'] = [ps('p1', repo=src['repo'])]
        known['pass_enumeration'] = 'complete'
        for merge in known['merges']:
            merge['pass_id'] = 'p1'
        good = '<!-- MACHINE-SUMMARY -->\n```json\n%s\n```\n' % json.dumps(analyze(known))
        check_report(good + '- **Merges per pass: 34**\n', known)
        for claim in ('- **Merges per pass: 99**', '> `ratio = UNKNOWN`', 'ratio: 0.5'):
            with self.subTest(claim=claim), self.assertRaises(Bad):
                check_report(good + claim + '\n', known)

    def test_receipt_row_id_and_group_position_are_bound(self):
        src = load_json('SOURCES.json')
        check_sources(src)
        for field, value in (('group_position', 999), ('row_id', 'wrong-row')):
            with self.subTest(field=field):
                bad = json.loads(json.dumps(src))
                bad['merges'][0][field] = value
                with self.assertRaisesRegex(Bad, 'receipt lines'):
                    check_sources(bad)
                del bad['merges'][0][field]
                with self.assertRaisesRegex(Bad, 'receipt lines'):
                    check_sources(bad)

    def test_report_check_rejects_false_ratio_and_tampered_sources(self):
        line = '2026-11-14 01:00:00 x-pr1 MERGED o/r#1 at ' + H('a') + ' (CI2-A group position 1)'
        m = parse_receipt(line)
        src = doc(merges=[dict(m, pass_id=None)], receipt_lines=[line], receipt_lines_sha256=lines_digest([line]),
                  pass_enumeration='none', missing_coverage=['pass ids'])
        good = '<!-- MACHINE-SUMMARY -->\n```json\n%s\n```\n' % json.dumps(analyze(src))
        self.assertEqual(check_report(good, src)['ratio'], None)
        with self.assertRaises(Bad):
            check_report(good + '\nratio: 0.5\n', src)
        with self.assertRaises(Bad):
            check_report(good.replace('"UNKNOWN"', '"KNOWN"'), src)
        bad = json.loads(json.dumps(src)); bad['merges'][0]['head'] = H('b')
        with self.assertRaises(Bad):
            check_report(good, bad)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--check')
    ap.add_argument('--sources')
    a = ap.parse_args(argv)
    if a.self_test:
        r = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
        return 0 if r.wasSuccessful() else 1
    if a.check and a.sources:
        try:
            cmd_check(a.check, a.sources)
        except (Bad, OSError) as e:
            print('CHECK FAIL: %s' % e, file=sys.stderr)
            return 1
        return 0
    ap.print_usage(sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
