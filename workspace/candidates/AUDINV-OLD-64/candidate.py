#!/usr/bin/env python3
"""Offline, read-only, source-bound retention gap report checker. No apply mode."""
import argparse
import copy
import hashlib
import json
import re
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
CLASSES = ('inbox-payloads', 'inbox-ids', 'mac-spool', 'relay-rows', 'relay-pictures',
           'screenshots', 'conversation-outbox', 'approval-change-release',
           'photo-originals', 'backups', 'mac-messages')
HEX = re.compile(r'[0-9a-f]{64}')
ACCEPTANCE = '\n## Actual local acceptance receipt\n'
EXPECTED_RECEIPT = ("\n```console\n"
    "$ python3 workspace/candidates/AUDINV-OLD-64/candidate.py --self-test\n"
    "SELF-TEST PASS: 6 named synthetic tests (local-only)\nexit: 0\n"
    "$ python3 workspace/candidates/AUDINV-OLD-64/candidate.py --check retention-access-enforcement-gap.md --sources SOURCES.json\n"
    "CHECK PASS: 11 classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0\nexit: 0\n```\n")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def pairs(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: require(False, 'nonfinite JSON'))


def keys(doc, expected):
    require(isinstance(doc, dict) and set(doc) == set(expected), 'unexpected schema fields')


def stamp(value):
    require(isinstance(value, str), 'timestamp type')
    dt = datetime.fromisoformat(value)
    require(dt.tzinfo is not None and dt.utcoffset() is not None, 'timestamp needs zone')
    return dt.astimezone(timezone.utc)


def local(raw):
    require(isinstance(raw, str) and bool(raw), 'missing path')
    p = Path(raw)
    require(not p.is_absolute() and '..' not in p.parts and p.parts, 'path escape')
    here = ROOT
    for part in p.parts:
        here = here / part
        require(not here.is_symlink(), 'symlink path')
    require(here.is_file() and ROOT in here.resolve().parents, 'not a package file')
    return here


def load(raw):
    return decode(local(raw).read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(s):
    keys(s, ('schema_version', 'base_sha', 'captured_at', 'sources', 'decisions', 'rows', 'limits'))
    require(type(s['schema_version']) is int and s['schema_version'] == 1, 'unknown schema')
    require(isinstance(s['base_sha'], str) and re.fullmatch('[0-9a-f]{40}', s['base_sha']), 'base identity')
    stamp(s['captured_at'])
    require(isinstance(s['sources'], list) and s['sources'], 'sources missing')
    ids = set()
    for src in s['sources']:
        keys(src, ('id', 'locator', 'sha256', 'captured_at', 'kind', 'excerpts'))
        require(re.fullmatch('[a-z][a-z0-9-]*', src['id']) and src['id'] not in ids, 'source identity')
        ids.add(src['id'])
        require(HEX.fullmatch(src['sha256']) and src['kind'] in ('repo-source', 'decision-excerpt'), 'source digest/kind')
        require(not Path(src['locator']).is_absolute() and '..' not in Path(src['locator']).parts, 'source locator')
        stamp(src['captured_at'])
        require(isinstance(src['excerpts'], list) and src['excerpts'], 'source excerpts missing')
        for excerpt in src['excerpts']:
            keys(excerpt, ('start', 'end', 'text'))
            require(type(excerpt['start']) is int and type(excerpt['end']) is int
                    and 0 < excerpt['start'] <= excerpt['end'] and isinstance(excerpt['text'], str), 'source range')
    require(len(s['rows']) == len(CLASSES), 'class count')
    require([r.get('class') for r in s['rows']] == list(CLASSES), 'class identity/order/duplicate')
    for row in s['rows']:
        keys(row, ('class', 'period', 'basis', 'mechanism', 'layers', 'measured', 'access', 'missing', 'verdict', 'refs'))
        require(row['refs'] and set(row['refs']) <= ids, 'missing source binding')
        require(all(isinstance(row[k], str) and row[k] for k in
                    ('period', 'basis', 'mechanism', 'measured', 'access', 'missing')), 'empty row')
        keys(row['layers'], ('counts', 'configured', 'code', 'installed', 'observed'))
        require(all(v in ('SOURCE', 'HISTORICAL', 'UNKNOWN', 'NOT-COUNTED')
                    for v in row['layers'].values()), 'evidence layer')
        require(row['layers']['configured'] == row['layers']['installed'] == row['layers']['observed'] == 'UNKNOWN',
                'no current configuration/install/observation receipt supplied')
        require(row['verdict'] == 'UNVERIFIED/HOLD', 'unsupported success')
    require(isinstance(s['decisions'], list) and len(s['decisions']) == 2, 'decision history')
    for decision in s['decisions']:
        keys(decision, ('date', 'ref', 'meaning'))
        stamp(decision['date'])
        require(decision['ref'] in ids and decision['meaning'], 'decision source')
    require(isinstance(s['limits'], list) and s['limits'], 'limits missing')
    # No private data is needed or admitted: field names and source locators only.
    text = json.dumps(s, ensure_ascii=False)
    require(not re.search(r'/home/|/Users/|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\+\d[\d ()-]{7,}', text),
            'private identifier/path')
    return s


def assess(case):
    """Synthetic qualification only; never owner agreement or action permission."""
    keys(case, ('class', 'period', 'receipt_class', 'receipt_period', 'layer', 'at', 'status', 'count'))
    require(case['class'] in CLASSES and case['receipt_class'] in CLASSES, 'class identity')
    require(case['layer'] in ('counts', 'configured', 'code', 'installed', 'observed'), 'layer')
    require(case['status'] in ('valid', 'cancelled', 'expired', 'duplicate', 'stale'), 'status')
    stamp(case['at'])
    require(case['count'] is None or type(case['count']) is int and case['count'] >= 0, 'count')
    return ('TECHNICAL-RECEIPT-ONLY' if case['layer'] == 'observed' and case['status'] == 'valid'
            and case['receipt_class'] == case['class'] and case['period'] == case['receipt_period']
            else 'UNVERIFIED/HOLD')


def render(s):
    validate(s)
    lines = ['# Retention and access enforcement gap — AUDINV-OLD-64', '',
        'CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. Overall: UNVERIFIED/HOLD.', '',
        f"Inspected main: `{s['base_sha']}`. Source capture: {s['captured_at']}.", '',
        '## Recorded decisions, not model-supplied owner acceptance', '']
    for d in s['decisions']:
        lines.append(f"- {d['date']}: {d['meaning']} [{d['ref']}]")
    lines += ['', 'Actual policy agreement and acceptance remain with the owner. No owner contact occurred.', '',
        '## Class-by-class comparison', '',
        'Counts, configured periods, implemented code, installed/enabled mechanisms and observed enforcement are separate layers.',
        'SOURCE means inspected code/documentation, not installed operation. HISTORICAL is a dated prior receipt, not current measurement.',
        'UNKNOWN is missing evidence, never a measured zero. All current configured/installed/observed layers are UNKNOWN.', '',
        '| Data class | Policy basis / period | Mechanism / receipt | Layers | Measured scope / date | Access boundary | Missing evidence | Verdict |',
        '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in s['rows']:
        layer = '; '.join(f'{k}={v}' for k, v in r['layers'].items())
        cells = [r['class'], f"{r['basis']}: {r['period']}", r['mechanism'] + ' [' + ', '.join(r['refs']) + ']',
                 layer, r['measured'], r['access'], r['missing'], r['verdict']]
        require(not any('|' in c or '\n' in c for c in cells), 'unsafe matrix text')
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines += ['', f'Totals: {len(s["rows"])} classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0.', '',
              '## Evidence limits and stop boundary', '']
    lines += ['- ' + limit for limit in s['limits']]
    lines += ['', '## Immutable sanitized sources', '']
    for src in s['sources']:
        lines += [f"### {src['id']}", f"`{src['locator']}`; SHA-256 `{src['sha256']}`; captured {src['captured_at']}; {src['kind']}."]
        for e in src['excerpts']:
            lines += [f"Lines {e['start']}-{e['end']}:", '```text', e['text'], '```']
    return '\n'.join(lines) + '\n'


def bound_sources(name):
    require(name == 'SOURCES.json', 'only admitted source manifest')
    bases = load('BASES.json')
    keys(bases, ('schema_version', 'base_sha', 'candidate_only', 'installed', 'no_apply', 'source_hashes', 'package_hashes'))
    require(type(bases['schema_version']) is int and bases['schema_version'] == 1
            and bases['candidate_only'] is True and bases['installed'] is False and bases['no_apply'] is True, 'base boundary')
    require(set(bases['package_hashes']) == {'SOURCES.json', 'fixtures.json', 'candidate.py'}, 'package bindings')
    for path, expected in bases['package_hashes'].items():
        require(HEX.fullmatch(expected) and digest(local(path).read_bytes()) == expected, 'package digest mismatch')
    s = validate(load(name))
    require(s['base_sha'] == bases['base_sha'], 'base mismatch')
    require({x['locator']: x['sha256'] for x in s['sources']} == bases['source_hashes'], 'source digest map mismatch')
    return s


def check(report, sources):
    # Validate BOTH caller paths before any content opens.
    rp, sp = local(report), local(sources)
    require(report == 'retention-access-enforcement-gap.md' and sources == 'SOURCES.json', 'unsupported artifact')
    s = bound_sources(sources)
    actual = rp.read_text(encoding='utf-8')
    expected = render(s)
    require(actual in (expected, expected + ACCEPTANCE + EXPECTED_RECEIPT), 'artifact does not match exact source-bound report/receipt')
    return 'CHECK PASS: 11 classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0'


class Acceptance(unittest.TestCase):
    def setUp(self):
        self.s = bound_sources('SOURCES.json')
        self.f = load('fixtures.json')
        keys(self.f, ('schema_version', 'synthetic', 'cases'))
        require(type(self.f['schema_version']) is int and self.f['schema_version'] == 1
                and self.f['synthetic'] is True, 'fixture schema')

    def test_each_policy_class_has_separate_enforcement_evidence(self):
        self.assertEqual(len(self.s['rows']), 11)
        for row in self.f['cases']:
            self.assertEqual(assess(row['input']), row['expected'], row['name'])
        bad = copy.deepcopy(self.s)
        bad['rows'][1] = bad['rows'][0]
        with self.assertRaises(ValueError): validate(bad)

    def test_report_counts_do_not_claim_deletion_enforcement(self):
        case = copy.deepcopy(self.f['cases'][0]['input'])
        for layer in ('counts', 'configured', 'code', 'installed'):
            case['layer'] = layer
            for count in (None, 0, 12):
                case['count'] = count
                self.assertEqual(assess(case), 'UNVERIFIED/HOLD')
        bad = copy.deepcopy(self.s)
        bad['rows'][0]['verdict'] = 'ENFORCED'
        with self.assertRaises(ValueError): validate(bad)

    def test_dated_approval_not_undated_owner_acceptance(self):
        self.assertEqual(self.s['decisions'][0]['date'], '2026-11-06T00:00:00-08:00')
        self.assertIn('once the spec lists them', render(self.s))
        self.assertIn('retire/delete HOLD', render(self.s))
        self.assertIn('Actual policy agreement and acceptance remain with the owner.', render(self.s))
        bad = copy.deepcopy(self.s)
        bad['decisions'][0]['date'] = '2026-11-06'
        with self.assertRaises(ValueError): validate(bad)

    def test_missing_transport_receipt_and_conflicting_period_stay_hold(self):
        for r in self.s['rows']:
            self.assertEqual(r['layers']['observed'], 'UNKNOWN')
        for status in ('cancelled', 'expired', 'duplicate', 'stale'):
            c = copy.deepcopy(self.f['cases'][0]['input'])
            c['status'] = status
            self.assertEqual(assess(c), 'UNVERIFIED/HOLD')
        c = copy.deepcopy(self.f['cases'][0]['input'])
        c['receipt_period'] = 'conflicting-period'
        self.assertEqual(assess(c), 'UNVERIFIED/HOLD')

    def test_no_private_identifiers_or_write_side_effects_in_report(self):
        before = {p: local(p).read_bytes() for p in ('SOURCES.json', 'fixtures.json', 'retention-access-enforcement-gap.md')}
        self.assertEqual(check('retention-access-enforcement-gap.md', 'SOURCES.json'),
                         'CHECK PASS: 11 classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0')
        for p, data in before.items(): self.assertEqual(local(p).read_bytes(), data)
        bad = copy.deepcopy(self.s)
        bad['rows'][0]['access'] = 'person@example.invalid'
        with self.assertRaises(ValueError): validate(bad)
        original = Path.read_text
        report = local('retention-access-enforcement-gap.md')
        def altered(path, *args, **kwargs):
            if path == report:
                return render(self.s).replace('UNVERIFIED/HOLD', 'ENFORCED')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'read_text', altered):
            with self.assertRaises(ValueError):
                check('retention-access-enforcement-gap.md', 'SOURCES.json')

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        for raw in ('{"schema_version":1,"schema_version":1}', '{bad', '{"n":NaN}'):
            with self.assertRaises(ValueError): decode(raw)
        for version in (2, True):
            bad = copy.deepcopy(self.s)
            bad['schema_version'] = version
            with self.assertRaises(ValueError): validate(bad)
        bad = copy.deepcopy(self.s)
        bad['sources'][0]['id'] = 'invalid identity'
        with self.assertRaises(ValueError): validate(bad)
        opened = []
        def unexpected(*a, **k):
            opened.append(a)
            raise AssertionError('disallowed content I/O')
        with patch.object(Path, 'open', unexpected):
            for raw in ('../outside', '/etc/passwd', '/home/user/.config/hass/host.json', ''):
                with self.assertRaises(ValueError): check('retention-access-enforcement-gap.md', raw)
            # Simulate a symlink component; no real link or protected file is opened.
            with patch.object(Path, 'is_symlink', return_value=True):
                with self.assertRaises(ValueError): local('SOURCES.json')
        self.assertEqual(opened, [])
        bad = copy.deepcopy(self.s)
        bad['rows'][0]['refs'] = ['absent']
        with self.assertRaises(ValueError): validate(bad)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--self-test', action='store_true')
    g.add_argument('--check')
    p.add_argument('--sources')
    a = p.parse_args(argv)
    try:
        if a.self_test:
            require(a.sources is None, 'unsupported flag combination')
            result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Acceptance))
            if not result.wasSuccessful(): return 1
            print('SELF-TEST PASS: 6 named synthetic tests (local-only)')
        else:
            require(a.sources is not None, '--sources required')
            print(check(a.check, a.sources))
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
