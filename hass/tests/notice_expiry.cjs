// No HTTP server: exercise the real inline script in an open Chromium page.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE);
const assert = require('node:assert/strict');
(async () => {
  let script = '';
  for await (const chunk of process.stdin) script += chunk;
  const browser = await chromium.launch({headless: true});
  const open = async (attrs, before) => {  // a page whose clock starts at `before` (UTC) and moves only when the test says
    const page = await browser.newPage();
    await page.clock.install({time: new Date(before)});
    await page.setContent(`<p class="home-notice"${attrs}>Closed today</p>${script}`);
    return page;
  };
  const shown = page => page.locator('.home-notice').isVisible();
  const fire = (page, name) => page.evaluate(n => (n === 'pageshow' ? window : document).dispatchEvent(new Event(n)), name);
  try {
    for (const [until, before] of [
      ['2026-11-26', '2026-11-27T07:59:45Z'], // PST
      ['2026-07-04', '2026-07-05T06:59:45Z'], // PDT
    ]) {
      const page = await open(` data-until="${until}"`, before);
      assert.equal(await shown(page), true);
      await page.clock.runFor(30000);
      assert.equal(await shown(page), false);
      await page.close();
    }
    console.log('PASS: continuously open notice expires across PST and PDT midnight');

    // AV2152-08: a notice with a first day stays hidden until that Pacific midnight, whatever the UTC date already says
    for (const [from, before] of [
      ['2026-11-27', '2026-11-27T07:59:45Z'], // PST midnight; UTC is already the 27th
      ['2026-07-05', '2026-07-05T06:59:45Z'], // PDT midnight
      ['2026-11-01', '2026-11-01T06:59:45Z'], // the day the clocks go back
      ['2026-03-08', '2026-03-08T07:59:45Z'], // the day the clocks go forward
    ]) {
      const page = await open(` hidden data-from="${from}" data-until="2027-01-30"`, before);
      assert.equal(await shown(page), false, `hidden before ${from}`);
      await page.clock.runFor(10000);
      assert.equal(await shown(page), false, `still hidden 5s before ${from}`);
      await page.clock.runFor(10000);
      assert.equal(await shown(page), true, `shown on ${from}`);
      await page.close();
    }
    console.log('PASS: continuously open notice appears at its first Pacific midnight');

    // first and last day are both inclusive: a one-day notice enters at midnight and leaves at the next one
    let page = await open(' hidden data-from="2026-11-26" data-until="2026-11-26"', '2026-11-26T07:59:45Z');
    assert.equal(await shown(page), false);
    await page.clock.runFor(30000);
    assert.equal(await shown(page), true);
    await page.clock.setSystemTime(new Date('2026-11-27T07:59:30Z'));  // 23:59:30 on that day, no timer ran in between
    await page.clock.runFor(2000);
    assert.equal(await shown(page), true);
    await page.clock.runFor(30000);
    assert.equal(await shown(page), false);
    await page.close();
    console.log('PASS: first and last day are inclusive');

    // hidden is assigned in both directions on load
    page = await open(' data-from="2026-12-01" data-until="2026-12-05"', '2026-11-20T20:00:00Z');
    assert.equal(await shown(page), false);
    await page.close();
    page = await open(' hidden data-from="2026-11-01" data-until="2026-12-05"', '2026-11-20T20:00:00Z');
    assert.equal(await shown(page), true);
    await page.close();
    console.log('PASS: hidden is assigned in both directions on load');

    // a page frozen in the background: time jumps without timers, pageshow / visibilitychange recover the state
    for (const event of ['pageshow', 'visibilitychange']) {
      page = await open(' hidden data-from="2026-12-01" data-until="2026-12-05"', '2026-11-20T20:00:00Z');
      assert.equal(await shown(page), false);
      await page.clock.setSystemTime(new Date('2026-12-02T20:00:00Z'));
      await fire(page, event);
      assert.equal(await shown(page), true, `shown after ${event}`);
      await page.clock.setSystemTime(new Date('2026-12-06T08:30:00Z'));  // 00:30 PST on the 6th
      await fire(page, event);
      assert.equal(await shown(page), false, `hidden after ${event}`);
      await page.close();
    }
    console.log('PASS: background and pageshow recovery');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
