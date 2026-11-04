// No HTTP server: exercise the real inline script in an open Chromium page.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
(async () => {
  let script = '';
  for await (const chunk of process.stdin) script += chunk;
  const browser = await chromium.launch({headless: true});
  try {
    for (const [until, before] of [
      ['2026-11-26', '2026-11-27T07:59:45Z'], // PST
      ['2026-07-04', '2026-07-05T06:59:45Z'], // PDT
    ]) {
      const page = await browser.newPage();
      await page.clock.install({time: new Date(before)});
      await page.setContent(`<p class="home-notice" data-until="${until}">Closed today</p>${script}`);
      assert.equal(await page.locator('.home-notice').isVisible(), true);
      await page.clock.runFor(30000);
      assert.equal(await page.locator('.home-notice').isVisible(), false);
      await page.close();
    }
    console.log('PASS: continuously open notice expires across PST and PDT midnight');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
