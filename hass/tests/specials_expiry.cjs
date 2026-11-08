// AVO-SPECIALS-1: run the real inline script in an open page; no server. Pacific midnight, PST and PDT.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
(async () => {
  let script = '';
  for await (const chunk of process.stdin) script += chunk;
  const browser = await chromium.launch({headless: true});
  try {
    for (const [end, before] of [['2026-11-26', '2026-11-27T07:59:45Z'], ['2026-07-04', '2026-07-05T06:59:45Z']]) {
      const page = await browser.newPage();
      await page.clock.install({time: new Date(before)});
      await page.setContent(`<section class="weekly-specials"><h2>x</h2><ul><li data-start="2026-01-01" data-end="${end}">A</li><li data-start="2026-01-01" data-end="2099-01-01">B</li></ul></section>${script}`);
      assert.equal(await page.locator('li:not([hidden])').count(), 2);
      await page.clock.runFor(30000);
      assert.equal(await page.locator('li:not([hidden])').count(), 1, 'the expired card hides, the other stays');
      assert.equal(await page.locator('.weekly-specials').isVisible(), true);
      await page.close();
      const lone = await browser.newPage();
      await lone.clock.install({time: new Date(before)});
      await lone.setContent(`<section class="weekly-specials"><h2>x</h2><ul><li data-start="2026-01-01" data-end="${end}">A</li></ul></section>${script}`);
      assert.equal(await lone.locator('.weekly-specials').isVisible(), true);
      await lone.clock.runFor(30000);
      assert.equal(await lone.locator('.weekly-specials').isVisible(), false, 'the last card expires: no heading left');
      await lone.close();
      const early = await browser.newPage();  // a card whose first day has not come stays hidden
      await early.clock.install({time: new Date(before)});
      await early.setContent(`<section class="weekly-specials"><ul><li data-start="2099-01-01" data-end="2099-01-05">A</li></ul></section>${script}`);
      assert.equal(await early.locator('.weekly-specials').isVisible(), false);
      await early.close();
    }
    console.log('PASS: cards and section hide across PST and PDT midnight');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
