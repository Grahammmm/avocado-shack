// RF1345-13: the trail-map QA fixture handler keeps reads inside its supplied tree. No browser, no port.
//   node --test storefront-mockup/trail-map-fixture-server.test.cjs
'use strict';
const test = require('node:test'), assert = require('node:assert/strict'), fs = require('fs'), os = require('os'), path = require('path');
const {createTrailFixtureHandler} = require('./trail-map-fixture-server.cjs');

const FIXTURE = '<!doctype html><div id="host" data-trail-explorer></div><script src="/trail-explorer.js"></script>';
const MARKER = 'SYNTHETIC OUTSIDE MARKER';
const WEBP = Buffer.from([0x52, 0x49, 0x46, 0x46, 0x04, 0, 0, 0, 0x57, 0x45, 0x42, 0x50, 0xff, 0x00]);

// <tmp>/site is the root; <tmp>/outside and <tmp>/site-evil (a name-prefix sibling) hold outside bytes.
function tree(t) {
  const tmp = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'trail-fixture-')));
  t.after(() => fs.rmSync(tmp, {recursive: true, force: true}));
  const site = path.join(tmp, 'site'), outside = path.join(tmp, 'outside'), evil = path.join(tmp, 'site-evil');
  for (const d of [site, path.join(site, 'assets/trails'), outside, evil]) fs.mkdirSync(d, {recursive: true});
  fs.writeFileSync(path.join(site, 'trail-explorer.js'), 'CONTROL SCRIPT');
  fs.writeFileSync(path.join(site, 'trail-explorer.css'), '.x{color:red}');
  fs.writeFileSync(path.join(site, 'assets/trails/point-buchon.json'), '{"ok":true}');
  fs.writeFileSync(path.join(site, 'assets/trails/point-buchon-topo.webp'), WEBP);
  fs.writeFileSync(path.join(site, 'notes.bin'), 'raw');
  fs.writeFileSync(path.join(outside, 'marker.txt'), MARKER);
  fs.writeFileSync(path.join(evil, 'marker.txt'), MARKER);
  return {tmp, site, outside, evil};
}

function call(handler, url) {
  const res = {statusCode: 200, headers: {}, body: undefined, ended: 0,
    setHeader(k, v) { this.headers[k.toLowerCase()] = v; }, end(b) { this.body = b; this.ended++; }};
  handler({method: 'GET', url}, res);
  assert.equal(res.ended, 1, url + ' ended once');
  return {status: res.statusCode, type: res.headers['content-type'], body: res.body === undefined ? '' : Buffer.from(res.body).toString()};
}

// Spy on every fs.readFileSync the handler makes; returns the resolved paths read.
function readSpy(t) {
  const orig = fs.readFileSync, reads = [];
  fs.readFileSync = function (p, ...rest) { try { reads.push(fs.realpathSync(String(p))); } catch { reads.push(String(p)); } return orig.call(this, p, ...rest); };
  t.after(() => { fs.readFileSync = orig; });
  return reads;
}
const notFound = r => assert.deepEqual([r.status, r.body], [404, 'no']);
const readsUnder = (reads, d) => reads.filter(p => p === d || p.startsWith(d + path.sep));

test('external_file_symlink_returns_404_without_read', t => {
  const {site, outside} = tree(t);
  fs.symlinkSync(path.join(outside, 'marker.txt'), path.join(site, 'linked.txt'));
  fs.symlinkSync(path.join(outside, 'marker.txt'), path.join(site, 'assets/trails/linked.json'));
  const h = createTrailFixtureHandler(site, FIXTURE), reads = readSpy(t);
  assert.deepEqual(call(h, '/trail-explorer.js'), {status: 200, type: 'text/javascript; charset=utf-8', body: 'CONTROL SCRIPT'});
  for (const url of ['/linked.txt', '/assets/trails/linked.json']) { const r = call(h, url); notFound(r); assert.ok(!r.body.includes(MARKER)); }
  assert.deepEqual(readsUnder(reads, outside), [], 'no byte read outside the root');
  assert.equal(fs.readFileSync(path.join(outside, 'marker.txt'), 'utf8'), MARKER);
});

test('external_directory_symlink_and_prefix_sibling_refuse', t => {
  const {tmp, site, outside, evil} = tree(t);
  fs.symlinkSync(outside, path.join(site, 'linked-dir'));
  fs.symlinkSync(evil, path.join(site, 'assets/evil-dir'));         // sibling whose name starts with "site"
  fs.symlinkSync(path.join(evil, 'marker.txt'), path.join(site, 'evil.txt'));
  fs.symlinkSync(tmp, path.join(site, 'up'));                         // the root's own parent
  const h = createTrailFixtureHandler(site, FIXTURE), reads = readSpy(t);
  for (const url of ['/linked-dir/marker.txt', '/assets/evil-dir/marker.txt', '/evil.txt', '/up/outside/marker.txt', '/up/site-evil/marker.txt', '/../site-evil/marker.txt', '/%2e%2e/outside/marker.txt'])
    notFound(call(h, url));
  assert.deepEqual(readsUnder(reads, outside).concat(readsUnder(reads, evil)), [], 'no byte read outside the root');
  assert.equal(call(h, '/up/site/trail-explorer.js').body, 'CONTROL SCRIPT', 'a link back into the root still serves');
});

test('dangling_cycle_missing_and_directory_targets_return_404', t => {
  const {site, tmp} = tree(t);
  fs.symlinkSync(path.join(site, 'gone.js'), path.join(site, 'dangling.js'));
  fs.symlinkSync(path.join(site, 'loop-b'), path.join(site, 'loop-a'));
  fs.symlinkSync(path.join(site, 'loop-a'), path.join(site, 'loop-b'));
  fs.symlinkSync(path.join(site, 'assets'), path.join(site, 'assets-link'));
  const h = createTrailFixtureHandler(site, FIXTURE), reads = readSpy(t);
  for (const url of ['/dangling.js', '/loop-a', '/loop-b/x.js', '/missing.js', '/assets', '/assets/', '/assets-link', '/', '']) {
    const r = call(h, url); notFound(r); assert.ok(!r.body.includes(tmp), 'no path disclosed');
  }
  assert.deepEqual(reads, [], 'nothing read for a 404');
});

test('ordinary_and_internal_link_resources_keep_bytes_and_mime', t => {
  const {site} = tree(t);
  fs.symlinkSync(path.join(site, 'trail-explorer.js'), path.join(site, 'alias.js'));
  fs.symlinkSync('trails', path.join(site, 'assets/trails-link'));    // relative in-root directory link
  const h = createTrailFixtureHandler(site, FIXTURE);
  assert.deepEqual(call(h, '/trail-explorer.js'), {status: 200, type: 'text/javascript; charset=utf-8', body: 'CONTROL SCRIPT'});
  assert.deepEqual(call(h, '/trail-explorer.css?v=2'), {status: 200, type: 'text/css', body: '.x{color:red}'});
  assert.deepEqual(call(h, '/assets/trails/point-buchon.json'), {status: 200, type: 'application/json', body: '{"ok":true}'});
  assert.deepEqual(call(h, '/notes.bin'), {status: 200, type: 'application/octet-stream', body: 'raw'});
  assert.deepEqual(call(h, '/alias.js'), {status: 200, type: 'text/javascript; charset=utf-8', body: 'CONTROL SCRIPT'});
  assert.deepEqual(call(h, '/assets/trails-link/point-buchon.json'), {status: 200, type: 'application/json', body: '{"ok":true}'});
  const res = {headers: {}, setHeader(k, v) { this.headers[k] = v; }, end(b) { this.body = b; }};
  h({url: '/assets/trails/point-buchon-topo.webp'}, res);
  assert.equal(res.headers['content-type'], 'image/webp');
  assert.ok(Buffer.compare(res.body, WEBP) === 0, 'webp bytes unchanged');
});

test('fixture_document_remains_in_memory', t => {
  const {tmp, site, outside} = tree(t);
  fs.writeFileSync(path.join(site, 'fixture'), 'DISK COPY');
  const alias = path.join(tmp, 'alias-root');
  fs.symlinkSync(site, alias);
  fs.symlinkSync(path.join(outside, 'marker.txt'), path.join(site, 'linked.txt'));
  const h = createTrailFixtureHandler(alias, FIXTURE), reads = readSpy(t);
  for (const url of ['/fixture', '/fixture?retry=1'])
    assert.deepEqual(call(h, url), {status: 200, type: 'text/html', body: FIXTURE});
  assert.deepEqual(reads, [], '/fixture reads no disk file');
  assert.equal(call(h, '/trail-explorer.js').body, 'CONTROL SCRIPT', 'a directory-alias root serves its files');
  notFound(call(h, '/linked.txt'));
  assert.deepEqual(readsUnder(reads, outside), []);
  assert.throws(() => createTrailFixtureHandler(path.join(site, 'trail-explorer.js'), FIXTURE), /not a directory/);
  assert.throws(() => createTrailFixtureHandler(path.join(tmp, 'no-such-root'), FIXTURE));
});

test('nonregular_and_read_error_targets_never_escape_handler', t => {
  const {site} = tree(t);
  const h = createTrailFixtureHandler(site, FIXTURE), js = path.join(site, 'trail-explorer.js'), css = path.join(site, 'trail-explorer.css');
  const orig = {statSync: fs.statSync, readFileSync: fs.readFileSync, realpathSync: fs.realpathSync};
  t.after(() => Object.assign(fs, orig));
  let reads = 0;
  fs.statSync = function (p, ...rest) { return p === js ? {isFile: () => false, isDirectory: () => false} : orig.statSync.call(this, p, ...rest); };
  fs.readFileSync = function (p, ...rest) { reads++; if (p === css) throw Object.assign(new Error('EACCES: ' + p), {code: 'EACCES'}); return orig.readFileSync.call(this, p, ...rest); };
  notFound(call(h, '/trail-explorer.js'));                          // e.g. a FIFO or socket: never read
  assert.equal(reads, 0);
  const r = call(h, '/trail-explorer.css'); notFound(r); assert.ok(!r.body.includes(site));
  fs.realpathSync = () => { throw Object.assign(new Error('EIO'), {code: 'EIO'}); };
  notFound(call(h, '/assets/trails/point-buchon.json'));
  Object.assign(fs, orig);
  assert.equal(call(h, '/trail-explorer.js').status, 200, 'handler keeps serving afterwards');
});
