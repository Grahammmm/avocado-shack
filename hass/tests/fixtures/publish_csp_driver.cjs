// AV1052-03: load the PUBLISHED home, /hike and 404 pages in Chromium and prove the Content-Security-Policy both ways.
// Input (stdin JSON): {normal, synthetic}: two folders written by sitegen.publish (outside the repository).
//   normal    today's real content: every page and interaction must finish with zero securitypolicyviolation events.
//   synthetic an active notice (hostile owner text), special and banner plus one checked product: still zero violations.
// A separate set of contexts injects what the policy must stop into the real governed document (parser HTML in the
// response, after the policy meta): each forbidden source is blocked with its directive, never runs, never reaches
// the network. The same markup in a page with the policy meta removed DOES run (so the markers prove something).
// Every off-origin request is aborted at the browser boundary and counted: the count must stay zero.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
const fs = require('node:fs'), http = require('node:http'), path = require('node:path');
const TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'};
const FOREIGN = 'http://foreign.test';
const CLOSED = /nothing was sent or saved/;

const serve = root => new Promise(resolve => {
  const missing = fs.readFileSync(path.join(root, '404.html'));
  const server = http.createServer((req, res) => {
    let file = path.join(root, decodeURIComponent(new URL(req.url, 'http://x').pathname));
    try { if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html'); } catch {}
    if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404, {'Content-Type': TYPES['.html']}); return res.end(missing); }
    res.writeHead(200, {'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream'});
    res.end(fs.readFileSync(file));
  });
  server.listen(0, '127.0.0.1', () => resolve({server, base: `http://127.0.0.1:${server.address().port}`}));
});

// A context that records the violated directive of every securitypolicyviolation (before any page script), page errors,
// and every request that would leave the loopback origin (aborted, never answered).
const watch = async (browser, base, options = {}) => {
  const ctx = await browser.newContext(options), seen = {violations: [], errors: [], foreign: [], consoleErrors: []};
  await ctx.addInitScript(() => document.addEventListener('securitypolicyviolation', e => console.debug('CSPVIOLATION ' + e.effectiveDirective)));
  ctx.on('console', m => { if (m.text().startsWith('CSPVIOLATION ')) seen.violations.push(m.text().slice(13)); });
  await ctx.route(url => new URL(url).origin !== base, route => { seen.foreign.push(route.request().method() + ' ' + new URL(route.request().url()).hostname); return route.abort(); });
  ctx.on('page', p => p.on('pageerror', e => seen.errors.push(e.message)));
  return {ctx, seen};
};
const clean = (seen, what) => {
  assert.ok(seen.violations.length === 0, what + ': CSP violations ' + seen.violations.join(','));
  assert.ok(seen.errors.length === 0, what + ': page errors ' + seen.errors.join(' | '));
  assert.ok(seen.foreign.length === 0, what + ': off-origin traffic ' + seen.foreign.join(','));
};
const closedForm = async (page, form) => {  // a script-forced submit on the closed signup still ends in the plain sentence
  await page.locator(form).evaluate(f => { f.querySelectorAll(':disabled').forEach(x => { x.disabled = false; }); f.noValidate = true; f.requestSubmit(); });
  await page.locator(form + ' .form-status').filter({hasText: CLOSED}).waitFor();
};
const mapReady = async page => { await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded(); await page.locator('[data-trail-explorer][data-ready=true]').waitFor({state: 'attached'}); };
const json = body => ({contentType: 'application/json', body: JSON.stringify(body)});

(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {normal, synthetic} = JSON.parse(input);
  const browser = await chromium.launch({headless: true});
  const servers = [];
  try {
    const site = await serve(normal); servers.push(site.server);
    const fake = await serve(synthetic); servers.push(fake.server);

    // 1. Normal published pages, phone and desktop: zero violations, zero page errors, nothing off-origin.
    for (const width of [390, 1440]) {
      const {ctx, seen} = await watch(browser, site.base, {viewport: {width, height: 900}});
      const page = await ctx.newPage();
      for (const route of ['/', '/hike', '/hike/', '/404.html', '/no-such-page', '/hike/nope/deeper']) {
        const status = (await page.goto(site.base + route)).status();
        assert.equal(status, /^\/(404\.html|no-such|hike\/nope)/.test(route) ? (route === '/404.html' ? 200 : 404) : 200, route);
        await page.waitForLoadState('networkidle');
        assert.ok(await page.locator('link[href*="style.css"]').count() > 0 && await page.locator('header .brand img').isVisible(), route + ': styled');
        await page.locator('[data-policy]').click(); assert.match(await page.locator('#dialog-content').innerText(), /doesn’t use cookies/); await page.keyboard.press('Escape');
        if (route === '/') { await page.locator('#catalog-grid article').first().waitFor(); await closedForm(page, '#community-newsletter'); }
        if (route.startsWith('/hike') && !route.includes('nope')) {
          await mapReady(page);
          await page.getByRole('button', {name: 'Enlarge map', exact: true}).click(); assert.equal(await page.locator('dialog[open]').count(), 1);
          await page.keyboard.press('Escape'); await closedForm(page, '#hike-updates');
        }
      }
      clean(seen, 'normal pages at ' + width); await ctx.close();
    }
    console.log('PASS: home, /hike, /hike/, 404 and deep 404 load and work with zero CSP violations (390 and 1440)');

    // 2. Synthetic owner states under the policy: notice, special, banner, availability, next hike, .ics, Maps link.
    {
      const {ctx, seen} = await watch(browser, fake.base, {viewport: {width: 1440, height: 900}});
      const event = {id: 'csp-1', title: 'Synthetic CSP hike', status: 'scheduled', startsAt: '2036-12-06T09:00:00-08:00', timezone: 'America/Los_Angeles',
        meetingPoint: 'Test trailhead', meetingAddress: '3 Example Road, Morro Bay, CA'};
      await ctx.route('**/community.json', r => r.fulfill(json({events: [event], routeIdeas: []})));
      const page = await ctx.newPage();
      await page.goto(fake.base + '/?view=all'); await page.locator('#catalog-grid article').first().waitFor(); await page.waitForLoadState('networkidle');
      const note = page.locator('.home-notice');
      assert.equal(await note.isVisible(), true, 'notice shown');
      assert.match(await note.innerText(), /<script>window\.__pwn=1<\/script>/, 'hostile owner text stays literal text');
      assert.equal(await page.locator('.home-notice script, .home-notice img, .home-notice [onerror]').count(), 0, 'no element came out of the notice text');
      assert.equal(await page.evaluate(() => window.__pwn), undefined, 'owner text never ran');
      assert.equal(await page.locator('main > .weekly-specials').isVisible(), true, 'special shown');
      assert.equal(await page.locator('[data-banner]').isVisible(), true, 'banner shown');
      assert.match(await page.locator('body').innerText(), /Available today/, 'checked availability badge');
      assert.match(await page.locator('#next-hike-line').innerText(), /^Next hike: .*December 6.* - Synthetic CSP hike$/, 'next-hike line');
      await page.goto(fake.base + '/hike/'); await page.locator('#upcoming-hikes article').first().waitFor();
      const maps = await page.locator('#upcoming-hikes a[href^="https://www.google.com/maps/"]').first().getAttribute('href');
      assert.ok(maps.includes(encodeURIComponent('3 Example Road, Morro Bay, CA')), 'Maps link');
      const [download] = await Promise.all([page.waitForEvent('download'), page.locator('a.hike-ics').first().click()]);
      assert.equal(download.suggestedFilename(), 'csp-1.ics');
      const ics = fs.readFileSync(await download.path(), 'utf8');
      assert.ok(ics.startsWith('BEGIN:VCALENDAR\r\n') && ics.includes('SUMMARY:Synthetic CSP hike') && ics.includes('LOCATION:Test trailhead'), '.ics bytes');
      clean(seen, 'synthetic owner states'); await ctx.close();
      console.log('PASS: notice with hostile text, special, banner, availability, next-hike line, .ics download and Maps link work under the policy');
    }

    // 3. Negative controls: the same real home page with forbidden sources injected after the policy meta.
    const hostile = `<script>window.__inline=1</script><button id="evil" onclick="window.__handler=1" style="color:red">x</button>`
      + `<script src="${FOREIGN}/x.js"></script><link rel="stylesheet" href="${FOREIGN}/x.css"><img src="${FOREIGN}/x.png" alt="">`
      + `<object data="${FOREIGN}/x.swf"></object><form id="evilform" action="${FOREIGN}/post" method="post"><button>go</button></form><base href="${FOREIGN}/">`;
    const poison = (ctx, base, stripPolicy) => ctx.route(base + '/', async route => {
      const res = await route.fetch(); let body = await res.text();
      if (stripPolicy) body = body.replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, '');
      return route.fulfill({response: res, body: body.replace('</body>', hostile + '</body>')});
    });
    {
      const {ctx, seen} = await watch(browser, site.base);
      await poison(ctx, site.base, false);
      const page = await ctx.newPage();
      await page.goto(site.base + '/'); await page.waitForLoadState('networkidle');
      await page.locator('#evil').click();
      await page.locator('#evilform button').click({noWaitAfter: true});
      const fetched = await page.evaluate(u => fetch(u).then(() => 'loaded', () => 'refused'), FOREIGN + '/data');
      assert.equal(fetched, 'refused', 'foreign fetch refused');
      const ran = await page.evaluate(() => ({inline: window.__inline, handler: window.__handler, base: document.baseURI}));
      assert.equal(ran.inline, undefined, 'inline script ran'); assert.equal(ran.handler, undefined, 'inline handler ran');
      assert.equal(ran.base, site.base + '/', 'foreign base applied');
      for (let i = 0; i < 50 && !seen.violations.includes('form-action'); i++) await page.waitForTimeout(100);  // the blocked navigation reports a moment after the click
      const got = new Set(seen.violations);
      for (const d of ['script-src-elem', 'script-src-attr', 'style-src-attr', 'style-src-elem', 'img-src', 'object-src', 'form-action', 'base-uri', 'connect-src'])
        assert.ok(got.has(d), 'expected a ' + d + ' violation, saw ' + [...got].join(','));
      assert.ok(seen.foreign.length === 0, 'a forbidden request reached the network boundary: ' + seen.foreign.join(','));
      await ctx.close();
      console.log('PASS: injected inline script, event attribute, inline style, foreign script/style/image/fetch, object, base and form are blocked with their directives and send nothing');
    }
    {  // control: with the policy meta removed the same markup runs, so the markers above mean something
      const {ctx, seen} = await watch(browser, site.base);
      await poison(ctx, site.base, true);
      const page = await ctx.newPage();
      await page.goto(site.base + '/'); await page.locator('#evil').click();
      assert.equal(await page.evaluate(() => [window.__inline, window.__handler].join()), '1,1', 'without a policy the markers run');
      assert.equal(seen.violations.length, 0); assert.ok(seen.foreign.length > 0, 'without a policy the foreign requests are attempted');
      await ctx.close();
      console.log('PASS: control: without the policy the same markup runs and reaches off-origin');
    }
  } finally {
    await browser.close(); servers.forEach(s => s.close());
  }
})().catch(e => { console.error(e); process.exit(1); });
