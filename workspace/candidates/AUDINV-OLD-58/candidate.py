#!/usr/bin/env python3
"""OLD-58: synthetic, candidate-only real Previewer/browser checks; never applies."""
import argparse
import copy
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timezone

ROOT = Path(__file__).absolute().parent
REPO = ROOT.parents[2]
CACHE = Path('/home/user/.cache/avo-ci-playwright/1.64.1')
MODULE = CACHE / 'node_modules/playwright'
CHROME = CACHE / 'browsers/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell'
NODE = Path('/home/user/.hermes/node/bin/node')
sys.dont_write_bytecode = True


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(name):
    p = ROOT / name
    if Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('package path required')
    if any(x.is_symlink() for x in (p, *p.parents)) or not p.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('symlink/path escape')
    return p


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def load(name):
    return json.loads(safe_path(name).read_text(), object_pairs_hook=pairs)


def fixtures(doc=None):
    doc = load('fixtures.json') if doc is None else doc
    if set(doc) != {'schema_version', 'records', 'cases'} or type(doc['schema_version']) is not int or doc['schema_version'] != 1:
        raise ValueError('fixture schema')
    seen = set()
    for row in doc['records']:
        if set(row) != {'id', 'name', 'description', 'maker', 'place', 'story', 'src', 'rgb'}:
            raise ValueError('record schema')
        if not re.fullmatch(r'synthetic-[ab]', row['id']) or row['id'] in seen:
            raise ValueError('record identity')
        seen.add(row['id'])
        if not re.fullmatch(r'assets/products/synthetic-[ab]\.png', row['src']):
            raise ValueError('asset identity')
        if not all(isinstance(row[k], str) and row[k] for k in ('name', 'description', 'maker', 'place', 'story')) or not isinstance(row['rgb'], list) or len(row['rgb']) != 3 or not all(type(n) is int and 0 <= n <= 255 for n in row['rgb']):
            raise ValueError('record content')
    if seen != {'synthetic-a', 'synthetic-b'}:
        raise ValueError('missing record')
    if doc['cases'] != {'positive': True, 'wrong_maker': False, 'stale_story': False, 'broken_image': False, 'wrong_src': False, 'wrong_bytes': False, 'external_get': False, 'post': False, 'other_loopback_port': False}:
        raise ValueError('case expectations')
    return doc


def browser_available():
    if not all(p.is_file() for p in (MODULE / 'package.json', CHROME, NODE)):
        return False
    return json.loads((MODULE / 'package.json').read_text())['version'] == '1.64.1'


def png(rgb):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 2, 2, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress((b'\0' + bytes(rgb) * 2) * 2)) + chunk(b'IEND', b'')


BROWSER = r"""'use strict';
const fs=require('fs'),crypto=require('crypto'),{chromium}=require(process.env.PLAYWRIGHT_MODULE);
const input=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const allowed=(url,method)=>{try{const u=new URL(url);return ['GET','HEAD'].includes(method)&&u.origin===input.base&&u.hostname==='127.0.0.1'}catch{return false}};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
 const receipt={browser:browser.version(),rows:[],blocked:[],cases:{}};
 try{
  for(const [viewport,size] of Object.entries({phone:{width:390,height:844},desktop:{width:1280,height:900}})){
   const page=await browser.newPage({viewport:size});
   await page.route('**/*',r=>allowed(r.request().url(),r.request().method())?r.continue():(receipt.blocked.push({url:r.request().url(),method:r.request().method()}),r.abort()));
   await page.goto(input.base,{waitUntil:'networkidle'});
   for(const expected of input.records){
    const card=page.locator(`article[data-product-id="${expected.id}"]`);
    const inspect=async()=>{
     const got=await card.evaluate(async el=>{
      const img=el.querySelector('img');let status=null,bytes=[];
      try{await img.decode()}catch{}
      try{const response=await fetch(img.currentSrc);status=response.status;bytes=Array.from(new Uint8Array(await response.arrayBuffer()))}catch{}
      return {name:el.querySelector('h2').textContent,description:el.querySelector('.food-description').textContent,
       maker:el.querySelector('.maker-name').textContent,place:el.querySelector('.origin-label').textContent,
       story:el.querySelector('.maker-story').textContent,src:img.getAttribute('src'),current:img.currentSrc,
       width:img.naturalWidth,height:img.naturalHeight,status,bytes};
     });
     got.sha256=crypto.createHash('sha256').update(Buffer.from(got.bytes)).digest('hex');delete got.bytes;
     const checks={name:got.name===expected.name,description:got.description===expected.description,
      maker:got.maker===expected.maker,place:got.place===`Based in ${expected.place}`,story:got.story===expected.story,
      src:got.src===expected.src&&got.current===input.base+'/'+expected.src,response:got.status===200,
      decoded:got.width>0&&got.height>0,identity:got.sha256===expected.sha256};
     return {id:expected.id,viewport,got,checks,ok:Object.values(checks).every(x=>x===true)};
    };
    receipt.rows.push(await inspect());
    if(expected.id==='synthetic-b'){
     const mutations={wrong_maker:['.maker-name','textContent','Wrong maker'],stale_story:['.maker-story','textContent','Old story'],
      broken_image:['img','src','assets/products/missing.png'],wrong_src:['img','src',input.records[0].src]};
     for(const [name,[selector,property,value]] of Object.entries(mutations)){
      const old=await card.locator(selector).evaluate((e,p)=>e[p],property);
      await card.locator(selector).evaluate((e,{property,value})=>{e[property]=value},{property,value});
      const result=await inspect();receipt.cases[viewport+':'+name]=!result.ok;
      await card.locator(selector).evaluate((e,{property,old})=>{e[property]=old},{property,old});
     }
     // A valid, decoded 200 image at the intended path is still wrong when its bytes differ.
     await page.route('**/synthetic-b.png',r=>r.fulfill({status:200,contentType:'image/png',body:Buffer.from(input.wrong_png,'hex')}));
     const wrong=await inspect();receipt.cases[viewport+':wrong_bytes']=wrong.got.status===200&&wrong.got.width>0&&!wrong.checks.identity;
     await page.unroute('**/synthetic-b.png');
    }
   }
   for(const [name,url,method] of [['external_get','https://example.invalid/never','GET'],['post',input.base+'/api/community/subscriptions','POST'],['other_loopback_port','http://127.0.0.1:1/never','GET']]){
    const denied=await page.evaluate(async({url,method})=>{try{await fetch(url,{method});return false}catch{return true}},{url,method});
    receipt.cases[viewport+':'+name]=denied;
   }
   await page.close();
  }
  console.log(JSON.stringify(receipt));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
"""


def git(wt, *args):
    return subprocess.run(['git', '-C', str(wt), *args], check=True, capture_output=True, text=True).stdout.strip()


def source_map():
    # Exact runtime import closure, plus browser/server source; no host config reads.
    sys.path.insert(0, str(REPO))
    from hass import preview
    paths = {Path(m.__file__).resolve() for name, m in tuple(sys.modules.items()) if name in ('hass', 'hass.preview', 'hass.content_model', 'hass.notice') and getattr(m, '__file__', None)}
    paths.update({REPO / 'hass/screenshot.cjs', REPO / 'storefront-mockup/community-server.py'})
    return preview, {str(p.relative_to(REPO)): digest(p.read_bytes()) for p in sorted(paths)}


def exercise():
    if not browser_available():
        return {'status': 'UNVERIFIED', 'reason': 'approved pinned browser unavailable'}
    preview, _ = source_map()
    records = copy.deepcopy(fixtures()['records'])
    # Resolve scratch before fixture setup; never use the host's default tempfile root.
    scratch = safe_path('.scratch')
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as raw:
        tmp = Path(raw).resolve()
        wt = tmp / 'writer'
        site = wt / preview.SITE
        (site / 'assets/products').mkdir(parents=True)
        shutil.copyfile(REPO / 'storefront-mockup/community-server.py', site / 'community-server.py')
        (site / 'community.json').write_text('{"events":[],"routeIdeas":[]}')
        cards, assets = [], {}
        for row in records:
            data = png(row['rgb'])
            row['sha256'] = digest(data)
            assets[preview.SITE + '/' + row['src']] = data
            cards.append('<article data-product-id="{id}"><h2>{name}</h2><p class="food-description">{description}</p><p class="maker-name">{maker}</p><p class="origin-label">Based in {place}</p><p class="maker-story">{story}</p><img src="{src}"></article>'.format(**{k: html.escape(v) for k, v in row.items() if isinstance(v, str)}))
        page = '<!doctype html><input id="product-search"><main id="catalog-grid">' + ''.join(cards) + '</main>'
        (site / 'index.html').write_text('<!doctype html><p>unchanged writer</p>')
        git(wt, 'init', '-q')
        git(wt, 'add', '.')
        before = git(wt, 'diff', '--cached')
        overlay = tmp / 'overlay'
        overlay.mkdir()
        copied = preview.Previewer(wt)._copy_site(overlay, {preview.SITE + '/index.html': page.encode()}, assets)
        assert all(not (site / r['src']).exists() for r in records)
        assert all(not (copied / r['src']).is_symlink() for r in records)
        env = {'PATH': str(NODE.parent) + ':/usr/bin:/bin', 'HOME': str(tmp), 'PLAYWRIGHT_MODULE': str(MODULE), 'CHROMIUM_PATH': str(CHROME), 'AVOSHACK_COMMUNITY_DB': str(tmp / 'empty.sqlite3'), 'AVOSHACK_COMMUNITY_CONFIG': str(copied / 'community.json')}
        server = subprocess.Popen([sys.executable, '-u', str(copied / 'community-server.py'), '--port', '0'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            import select
            assert server.stdout is not None
            if not select.select([server.stdout], [], [], 10)[0]:
                raise RuntimeError('fixture server startup timeout')
            line = server.stdout.readline()
            match = re.search(r'http://127\.0\.0\.1:\d+', line)
            if not match:
                raise RuntimeError('fixture server did not report loopback port')
            base = match.group()
            import http.client
            connection = http.client.HTTPConnection('127.0.0.1', int(base.rsplit(':', 1)[1]), timeout=10)
            connection.request('GET', '/api/community')
            response = connection.getresponse()
            assert response.status == 200
            response.read()
            connection.close()
            baseline = {}
            for row in records:
                for viewport in ('phone', 'desktop'):
                    target = {'kind': 'product', 'id': row['id'], 'name': row['name'], 'status': 'active', 'description': row['description'], 'image': row['src']}
                    proc = subprocess.run([str(NODE), str(preview.SCRIPT)], env={**env, 'PREVIEW_URL': base, 'TARGET': json.dumps(target), 'OUT': str(tmp / 'shot.png'), 'VIEWPORT': viewport}, capture_output=True, text=True, timeout=90)
                    if proc.returncode:
                        raise RuntimeError(proc.stderr)
                    baseline[row['id'] + ':' + viewport] = json.loads(proc.stdout)['checks']
            # Reproduce the exact gap: current product checks accept wrong maker/story
            # and different, still-decodable bytes at the expected second-record src.
            second = records[1]
            (copied / 'index.html').write_text(page.replace(second['maker'], 'Wrong maker').replace(second['story'], 'Old story'))
            (copied / second['src']).write_bytes(png([0, 0, 0]))
            weak = {}
            for viewport in ('phone', 'desktop'):
                target = {'kind': 'product', 'id': second['id'], 'name': second['name'], 'status': 'active', 'description': second['description'], 'image': second['src']}
                proc = subprocess.run([str(NODE), str(preview.SCRIPT)], env={**env, 'PREVIEW_URL': base, 'TARGET': json.dumps(target), 'OUT': str(tmp / 'weak.png'), 'VIEWPORT': viewport}, capture_output=True, text=True, timeout=90)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                weak[viewport] = json.loads(proc.stdout)['checks']
            (copied / 'index.html').write_text(page)
            (copied / second['src']).write_bytes(png(second['rgb']))
            (tmp / 'browser.cjs').write_text(BROWSER)
            (tmp / 'input.json').write_text(json.dumps({'base': base, 'records': records, 'wrong_png': png([0, 0, 0]).hex()}))
            proc = subprocess.run([str(NODE), str(tmp / 'browser.cjs'), str(tmp / 'input.json')], env=env, capture_output=True, text=True, timeout=90)
            if proc.returncode:
                raise RuntimeError(proc.stderr)
            receipt = json.loads(proc.stdout)
            receipt['run_state'] = 'completed'
            receipt['baseline'] = baseline
            receipt['baseline_wrong_second_record'] = weak
            import sqlite3
            with sqlite3.connect(tmp / 'empty.sqlite3') as db:
                receipt['empty_database'] = all(db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0] == 0 for table in ('subscriptions', 'rsvps'))
            receipt['writer_unchanged'] = git(wt, 'diff', '--cached') == before and all(not (site / r['src']).exists() for r in records)
            receipt['status'] = 'PASS' if qualified(receipt) else 'FAIL'
            return receipt
        finally:
            server.terminate()
            server.communicate(timeout=10)


def qualified(receipt):
    rows = receipt.get('rows', [])
    expected = {(r, v) for r in ('synthetic-a', 'synthetic-b') for v in ('phone', 'desktop')}
    cases = {v + ':' + case for v in ('phone', 'desktop') for case in fixtures()['cases'] if case != 'positive'}
    return (receipt.get('run_state') == 'completed' and len(rows) == 4 and {(r['id'], r['viewport']) for r in rows} == expected
            and all(row_valid(r) for r in rows)
            and set(receipt['cases']) == cases and all(v is True for v in receipt['cases'].values())
            and len(receipt['blocked']) == 6 and receipt['writer_unchanged'] is True and receipt['empty_database'] is True
            and set(receipt['baseline_wrong_second_record']) == {'phone', 'desktop'}
            and set(receipt['baseline']) == {r + ':' + v for r, v in expected}
            and all(set(c) == {'productShown', 'description', 'imageShown', 'noPageErrors', 'noPosts'} and all(v is True for v in c.values()) for c in [*receipt['baseline'].values(), *receipt['baseline_wrong_second_record'].values()]))


def row_valid(row):
    expected = next(r for r in fixtures()['records'] if r['id'] == row['id'])
    got = row['got']
    return (row['ok'] is True and set(row['checks']) == {'name', 'description', 'maker', 'place', 'story', 'src', 'response', 'decoded', 'identity'}
            and all(v is True for v in row['checks'].values())
            and all(got[k] == expected[k] for k in ('name', 'description', 'maker', 'story', 'src'))
            and got['place'] == 'Based in ' + expected['place'] and got['status'] == 200
            and got['width'] == 2 and got['height'] == 2 and got['sha256'] == digest(png(expected['rgb']))
            and re.fullmatch(r'http://127\.0\.0\.1:[1-9][0-9]*/' + re.escape(expected['src']), got['current']) is not None)


def check(report_name, sources_name):
    text = safe_path(report_name).read_text()
    sources = load(sources_name)
    payload = json.loads(text.split('```json\n', 1)[1].split('\n```', 1)[0], object_pairs_hook=pairs)
    if set(sources) != {'schema_version', 'base', 'captured_at', 'digests', 'receipt', 'missing'} or type(sources['schema_version']) is not int or sources['schema_version'] != 1:
        raise ValueError('source schema')
    if not re.fullmatch(r'[0-9a-f]{40}', sources['base']) or not sources['captured_at'].endswith('+00:00'):
        raise ValueError('source identity/time')
    datetime.fromisoformat(sources['captured_at'])
    _, current = source_map()
    bases = load('BASES.json')
    if type(bases.get('schema_version')) is not int or bases['schema_version'] != 1 or any(bases.get(k) is not v for k, v in {'candidate': True, 'installed': False, 'no_apply': True}.items()):
        raise ValueError('base schema/boundary')
    if bases.get('candidate_sha256') != digest(safe_path('candidate.py').read_bytes()) or bases.get('fixtures_sha256') != digest(safe_path('fixtures.json').read_bytes()):
        raise ValueError('candidate/fixture bindings')
    if sources['digests'] != current or sources['digests'] != bases['digests'] or sources['base'] != bases['base']:
        raise ValueError('source bindings')
    if payload != {'schema_version': 1, 'sources_sha256': digest(safe_path(sources_name).read_bytes()), 'status': sources['receipt']['status'], 'qualification': 'REVIEW_REQUIRED', 'installed': False}:
        raise ValueError('report binding/schema')
    receipt = sources['receipt']
    if receipt['status'] == 'PASS':
        if not qualified(receipt):
            raise ValueError('incomplete success')
    elif receipt['status'] != 'UNVERIFIED' or receipt.get('reason') != 'approved pinned browser unavailable':
        raise ValueError('unsupported status')
    if sources['missing'] != ['physical phone', 'live site', 'owner semantic acceptance', 'editor-to-proposal journey']:
        raise ValueError('missing coverage')
    print('CHECK PASS: exact source bindings; candidate-only; semantic acceptance UNVERIFIED')


class CandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = exercise()

    def require_browser(self):
        if self.receipt['status'] == 'UNVERIFIED':
            self.skipTest(self.receipt['reason'])

    def test_new_photo_resource_decodes_only_in_isolated_overlay(self):
        self.require_browser()
        self.assertTrue(self.receipt['writer_unchanged'])
        self.assertTrue(all(r['checks']['decoded'] and r['checks']['identity'] for r in self.receipt['rows']))

    def test_every_touched_record_and_both_viewports_are_checked(self):
        self.require_browser()
        self.assertTrue(qualified(self.receipt))
        for mutation in ('cancelled', 'expired', 'duplicate', 'stale'):
            damaged = copy.deepcopy(self.receipt)
            if mutation == 'duplicate':
                damaged['rows'][-1] = damaged['rows'][0]
            elif mutation == 'stale':
                damaged['rows'][-1]['checks']['identity'] = False
            else:
                damaged['run_state'] = mutation
            self.assertFalse(qualified(damaged), mutation)
        damaged = copy.deepcopy(self.receipt)
        damaged['rows'][-1]['got']['maker'] = 'Wrong maker despite claimed true checks'
        self.assertFalse(qualified(damaged))
        damaged['rows'].pop()
        self.assertFalse(qualified(damaged))

    def test_second_record_wrong_maker_text_or_broken_image_fails(self):
        self.require_browser()
        self.assertTrue(all(self.receipt['cases'].values()))

    def test_external_post_symlink_and_asset_escape_are_refused(self):
        preview, _ = source_map()
        scratch = safe_path('.scratch')
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as raw:
            root = Path(raw)
            outside = root / 'untouched'
            outside.write_bytes(b'unchanged')
            (root / preview.SITE).mkdir()
            (root / preview.SITE / 'link').symlink_to(outside)
            for files in ({preview.SITE + '/link': b'bad'}, {'../escape': b'bad'}, {preview.SITE + '/assets/products/a': b'bad'}):
                with self.assertRaises((ValueError, OSError)):
                    preview._write_overlay(root, files)
            for path in ('../bad', preview.SITE + '/assets/products/../bad', preview.SITE + '/assets/products/sub/bad'):
                with self.assertRaises(ValueError):
                    preview._asset_plan({path: b'bad'})
            self.assertEqual(outside.read_bytes(), b'unchanged')
        self.require_browser()
        self.assertEqual(len(self.receipt['blocked']), 6)

    def test_missing_browser_produces_unverified_not_success(self):
        from unittest.mock import patch
        with patch(__name__ + '.browser_available', return_value=False):
            self.assertEqual(exercise()['status'], 'UNVERIFIED')

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        from unittest.mock import patch
        with patch('io.open', side_effect=AssertionError('disallowed open')) as opened:
            for name in ('../RESULT.md', '/etc/passwd', '../../.local/share/private'):
                with self.assertRaises(ValueError):
                    load(name)
            opened.assert_not_called()
        scratch = safe_path('.scratch')
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as raw:
            link = Path(raw) / 'link'
            link.symlink_to(ROOT / 'fixtures.json')
            with self.assertRaises(ValueError):
                load(str(link.relative_to(ROOT)))
        for text in ('{"schema_version":1,"schema_version":1}', '{bad'):
            with self.assertRaises(ValueError):
                json.loads(text, object_pairs_hook=pairs)
        with tempfile.TemporaryDirectory(dir=scratch) as raw:
            for mutation in ('schema', 'timestamp', 'digest', 'false_success'):
                sources = copy.deepcopy(load('SOURCES.json'))
                if mutation == 'schema':
                    sources['schema_version'] = 99
                elif mutation == 'timestamp':
                    sources['captured_at'] = 'invalid'
                elif mutation == 'digest':
                    sources['digests'] = {}
                else:
                    sources['receipt'] = {'status': 'PASS', 'rows': []}
                sp, rp = Path(raw) / 'sources.json', Path(raw) / 'report.md'
                sp.write_text(json.dumps(sources))
                rp.write_text('```json\n' + json.dumps({'schema_version': 1, 'sources_sha256': digest(sp.read_bytes()), 'status': 'PASS', 'qualification': 'REVIEW_REQUIRED', 'installed': False}) + '\n```')
                with self.assertRaises(ValueError):
                    check(str(rp.relative_to(ROOT)), str(sp.relative_to(ROOT)))
        for mutation in ('schema', 'duplicate', 'identity', 'missing'):
            doc = copy.deepcopy(fixtures())
            if mutation == 'schema':
                doc['schema_version'] = 99
            elif mutation == 'missing':
                doc['records'].pop()
            else:
                doc['records'][1]['id'] = 'synthetic-a' if mutation == 'duplicate' else 'private-owner'
            with self.assertRaises(ValueError):
                fixtures(doc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument('--self-test', action='store_true')
    actions.add_argument('--browser', action='store_true', help='synthetic loopback receipt only')
    actions.add_argument('--check')
    parser.add_argument('--sources')
    args = parser.parse_args()
    if args.sources and not args.check:
        parser.error('--sources requires --check')
    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        print('BROWSER ' + CandidateTests.receipt['status'])
        return 0 if result.wasSuccessful() else 1
    if args.check:
        if not args.sources:
            parser.error('--check requires --sources')
        check(args.check, args.sources)
    else:
        receipt = exercise()
        preview, digests = source_map()
        base = load('BASES.json')['base']
        sources = {'schema_version': 1, 'base': base, 'captured_at': datetime.now(timezone.utc).isoformat(), 'digests': digests, 'receipt': receipt, 'missing': ['physical phone', 'live site', 'owner semantic acceptance', 'editor-to-proposal journey']}
        safe_path('SOURCES.json').write_text(json.dumps(sources, indent=2) + '\n')
        print(json.dumps({'status': receipt['status'], 'records': len(receipt.get('rows', [])), 'browser': receipt.get('browser', 'UNVERIFIED')}))
        return 0 if receipt['status'] in ('PASS', 'UNVERIFIED') else 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        print('REFUSED: ' + str(exc), file=sys.stderr)
        sys.exit(1)
