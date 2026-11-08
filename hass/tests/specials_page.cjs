// AVO-SPECIALS-1: the whole generated page in Chromium with a fixed clock: phone and desktop screenshots while the
// specials are live, then the section gone five days later without a reload. Input (stdin JSON): html, root, shots, today.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const TYPES = {'.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp'};
(async () => {
  let input = '';
  for await (const chunk of process.stdin) input += chunk;
  const {html, root, shots, today} = JSON.parse(input);
  const noon = new Date(today + 'T20:00:00Z');  // noon Pacific (UTC-8 or -7) on the build day
  const browser = await chromium.launch({headless: true});
  try {
    for (const [name, size] of [['phone', {width: 390, height: 844}], ['desktop', {width: 1280, height: 900}]]) {
      const page = await browser.newPage({viewport: size});
      await page.route('http://shack.test/**', route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/') return route.fulfill({status: 200, contentType: 'text/html', body: html});
        const file = path.join(root, decodeURIComponent(url.pathname));
        if (!file.startsWith(root) || !fs.existsSync(file) || !fs.statSync(file).isFile()) return route.fulfill({status: 404, body: ''});
        return route.fulfill({status: 200, contentType: TYPES[path.extname(file)] || 'application/octet-stream', body: fs.readFileSync(file)});
      });
      await page.clock.install({time: noon});
      await page.goto('http://shack.test/');
      const section = page.locator('main > .weekly-specials');
      assert.equal(await section.isVisible(), true);
      assert.equal(await section.locator('h2').innerText(), 'This week’s specials');
      assert.equal(await section.locator('li:not([hidden])').count(), 2);
      const box = await section.boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= size.width + 1, 'no sideways overflow');
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'page fits the width');
      if (shots) await section.screenshot({path: path.join(shots, `specials-${name}.png`)});
      if (shots && name === 'phone') await page.screenshot({path: path.join(shots, 'specials-phone-top.png')});
      await page.clock.fastForward(5 * 24 * 3600 * 1000);  // five days later, same open page
      assert.equal(await section.isVisible(), false, 'expired: the page hides the whole section');
      await page.close();
    }
    console.log('PASS: section shown on phone and desktop, hidden after its end date');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
