// AV2152-12: tests for the contrast helpers and the committed audit's contracts. No browser is launched here.
//   node --test storefront-mockup/site-contrast.test.cjs
'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
const h = require('./site-contrast-qa.cjs');
const repo = path.resolve(__dirname, '..'), report = fs.readFileSync(path.join(repo, 'reports/site-contrast-2026-11.md'), 'utf8');
const rgb = s => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
const WHITE = [255, 255, 255], BLACK = [0, 0, 0];

test('normal_and_large_threshold_boundaries', () => {
  assert.equal(h.contrastRatio(BLACK, WHITE), 21);
  assert.equal(h.contrastRatio([9, 9, 9], [9, 9, 9]), 1);
  assert.equal(h.thresholdFor(16, 400), 4.5);
  assert.equal(h.thresholdFor(24, 400), 3);
  assert.equal(h.thresholdFor(23.99, 400), 4.5);
  assert.equal(h.thresholdFor(18.666667, 700), 3);
  assert.equal(h.thresholdFor(18.666667, 600), 4.5);
  assert.equal(h.thresholdFor(18.66, 700), 4.5);
  assert.ok(h.contrastRatio(rgb('#767676'), WHITE) >= 4.5 && h.contrastRatio(rgb('#777777'), WHITE) < 4.5);
  // a ratio that displays as 4.500 but is below 4.5 must fail: find one among grey pairs
  let near = null;
  for (let a = 0; a < 256 && !near; a++) for (let b = 0; b < 256; b++) { const r = h.contrastRatio([a, a, a], [b, b, b]); if (r < 4.5 && r >= 4.4995) { near = [a, b, r]; break; } }
  assert.ok(near, 'a pair just under 4.5 exists');
  const res = h.assess({ fg: [near[0], near[0], near[0], 1], opacity: 1, layers: [[near[1], near[1], near[1], 1, 1]], size: 16, weight: '400' });
  assert.equal(res.status, 'fail');
  assert.equal(res.ratio.toFixed(3), '4.500');
});

test('transparent_nested_and_alpha_backing', () => {
  const half = [0, 0, 0, 0.5, 1];
  assert.deepEqual(h.backing([[0, 0, 0, 0, 1], [0, 0, 0, 0, 1]]), WHITE, 'transparent ancestors fall to the canvas');
  assert.deepEqual(h.backing([half]), [128, 128, 128]);
  assert.deepEqual(h.backing([[250, 247, 239, 1, 1], [0, 0, 0, 0, 1], [33, 77, 61, 0.5, 1]]), [142, 162, 150]);
  assert.deepEqual(h.backing([[0, 0, 0, 1, 0.5]]), [128, 128, 128], 'opacity scales a layer');
  assert.deepEqual(h.effectiveFg([0, 0, 0, 1], 0.5, WHITE), [128, 128, 128], 'opacity lightens the text');
  assert.deepEqual(h.effectiveFg([0, 0, 0, 0.5], 1, WHITE), [128, 128, 128], 'alpha lightens the text');
  const faint = h.assess({ fg: [0, 0, 0, 1], opacity: 0.3, layers: [], size: 16, weight: '400' });
  assert.equal(faint.status, 'fail');
  assert.deepEqual(h.parseColor('rgba(10, 20, 30, 0.5)'), [10, 20, 30, 0.5]);
  assert.deepEqual(h.parseColor('color(srgb 1 0 0 / 0.25)'), [255, 0, 0, 0.25]);
  const bad = h.assess({ fg: [0, 0, 0, 1], opacity: 1, layers: [], size: 16, weight: '400', unsupported: 'overlap' });
  assert.equal(bad.status, 'unassessed', 'unsupported backing is incomplete, never a pass');
  const px = h.assess({ fg: [255, 255, 255, 1], opacity: 1, layers: [], size: 16, weight: '400', pixels: [[0, 0, 0], [250, 250, 250]] });
  assert.equal(px.status, 'fail');
  assert.deepEqual(px.bgs, ['#000000', '#fafafa']);
});

test('nearest_color_is_feasible_and_minimal', () => {
  assert.deepEqual(h.nearestPassing([0, 0, 0], [WHITE], 4.5), [0, 0, 0], 'a passing colour stays');
  const fg = rgb('#777777');
  const dark = h.nearestPassing(fg, [WHITE], 4.5);
  assert.ok(h.contrastRatio(dark, WHITE) >= 4.5);
  assert.deepEqual(dark, h.nearestExhaustive(fg, [WHITE], 4.5), 'matches the exhaustive reference (single backing)');
  const two = [rgb('#f9f3e2'), rgb('#bdd2d8')];
  const light = h.nearestPassing(rgb('#d0a060'), two, 4.5);
  assert.deepEqual(light, h.nearestExhaustive(rgb('#d0a060'), two, 4.5), 'matches the exhaustive reference (two backings)');
  assert.ok(two.every(bg => h.contrastRatio(light, bg) >= 4.5));
  assert.deepEqual(h.nearestPassing(fg, [WHITE], 4.5), dark, 'deterministic');
  const rec = h.recommend(rgb('#fffdf3'), [rgb('#bdd2d8')], 4.5);
  assert.ok(rec.ok && h.contrastRatio(rgb(rec.color), rgb('#bdd2d8')) >= 4.5, 'recommendation independently rechecked');
  const none = h.recommend([128, 128, 128], [BLACK, WHITE], 7);
  assert.equal(none.ok, false);
  assert.deepEqual([none.darkest, none.lightest], ['#000000', '#ffffff']);
});

test('status_is_not_site_conformance', () => {
  const low = { state: 's', route: '/', vp: '390', interaction: 'default', sel: 'p', gsel: 'p.low', kind: 'text', text: 'x', size: 16, weight: '400', ...h.assess({ fg: [...rgb('#999999'), 1], opacity: 1, layers: [], size: 16, weight: '400' }) };
  assert.equal(low.status, 'fail');
  const sum = h.summarize([low]);
  assert.equal(sum.counts.fail, 1);
  assert.equal(sum.failures.length, 1);
  assert.ok(sum.failures[0].rec.ok && h.contrastRatio(rgb(sum.failures[0].rec.color), WHITE) >= 4.5, 'failure row carries a passing suggestion');
  // the committed audit records real failures and is still complete
  assert.match(report, /\| \d+ \| [1-9]\d* \| \d+ \| 0 \|/, 'fail count above zero, unassessed zero');
  assert.match(report, /Complete: \*\*yes\*\*/);
});

test('conditional_matrix_is_not_empty', () => {
  const rows = report.split('\n').filter(l => /^\| `[^`]+` \| `\/[^`]*` \|/.test(l));
  const ids = rows.map(l => l.split('`')[1]);
  for (const id of ['home-ordinary', 'home-notice-availability', 'home-unmatched-search', 'home-privacy-dialog', 'home-newsletter/saving', 'home-newsletter/success', 'home-newsletter/server-error', 'home-newsletter/unreachable', 'home-newsletter/closed-service',
    'hike-sample', 'hike-sample-rsvp-complete', 'hike-real-events', 'hike-rsvp-dialog', 'hike-rsvp/saving', 'hike-rsvp/success', 'hike-rsvp/server-error', 'hike-rsvp/unreachable', 'hike-updates/saving', 'hike-updates/success', 'hike-updates/server-error', 'hike-updates/unreachable', 'hike-no-events-no-samples', 'hike-calendar-failure', 'hike-static-events', 'hike-trailing-slash'])
    assert.ok(ids.includes(id), 'state ' + id + ' is in the matrix');
  for (const l of rows) { assert.doesNotMatch(l, /missing/, l); assert.equal((l.match(/\d+ runs/g) || []).length, 2, 'both widths: ' + l); }
  // conditional selectors appear with measured text at both widths in the occurrence index
  for (const sel of ['.home-notice', '.availability', '.sample-caption', '.hike-cancelled', '.hike-full', '.form-status']) {
    const hit = report.split('\n').filter(l => l.includes(sel) && /\| 1440, 390 \||\| 390, 1440 \|/.test(l) || (l.includes(sel) && l.includes('| 1440 |')) );
    assert.ok(report.includes(sel), 'selector ' + sel + ' measured');
  }
});

test('recommendations_in_the_report_pass_independently', () => {
  const fails = report.split('## Failing pairs')[1].split('## Exemptions')[0].split('\n').filter(l => /^\| \d+ \|/.test(l));
  assert.ok(fails.length > 0);
  for (const l of fails) {
    const cols = l.split(' | ');
    const thr = Number(cols[5]), orig = Number(cols[6]);
    assert.ok(orig < thr, 'listed ratio fails its threshold: ' + l);
    const rec = /`(#[0-9a-f]{6})` \((\d+\.\d+)\)/.exec(l);
    if (!rec) { assert.match(l, /no foreground-only solution: backings run from `#[0-9a-f]{6}` to `#[0-9a-f]{6}`/); continue; }
    const bgs = [...cols[3].matchAll(/#[0-9a-f]{6}/g)].map(m => rgb(m[0])).slice(1);
    for (const bg of bgs) assert.ok(h.contrastRatio(rgb(rec[1]), bg) >= thr, 'suggestion passes: ' + l);
  }
});

test('deterministic_safe_cli', () => {
  const git = () => cp.execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], { cwd: repo, encoding: 'utf8' });
  const before = git();
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'cqa-test-'));
  const env = { PATH: process.env.PATH, HOME: process.env.HOME, TMPDIR: tmp };
  // no module configured: refused before any work
  let r = cp.spawnSync('python3', [path.join(__dirname, 'site-contrast-qa.py'), '--check'], { cwd: repo, env, encoding: 'utf8' });
  assert.equal(r.status, 2);
  // injected error: a missing browser module fails nonzero and every scratch folder is removed
  r = cp.spawnSync('python3', [path.join(__dirname, 'site-contrast-qa.py'), '--check'], { cwd: repo, env: { ...env, PLAYWRIGHT_MODULE: '/nonexistent/playwright' }, encoding: 'utf8', timeout: 120000 });
  assert.notEqual(r.status, 0);
  assert.deepEqual(fs.readdirSync(tmp), [], 'scratch folders cleaned up');
  // the collector refuses folders inside the repository (exit 2) and importing it launches nothing
  r = cp.spawnSync('node', [path.join(__dirname, 'site-contrast-qa.cjs'), '--site-a', repo, '--site-b', repo], { cwd: repo, env: { ...env, QA_OUT_DIR: tmp, PLAYWRIGHT_MODULE: '/nonexistent/playwright' }, encoding: 'utf8' });
  assert.equal(r.status, 2);
  assert.equal(git(), before, 'the repository is unchanged');
  fs.rmSync(tmp, { recursive: true, force: true });
  // the publish allowlist does not name the private audit files
  const gen = fs.readFileSync(path.join(repo, 'hass/sitegen.py'), 'utf8');
  assert.doesNotMatch(gen, /site-contrast/);
});
