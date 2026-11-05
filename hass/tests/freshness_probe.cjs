// AV1622-04: run the real freshness block of storefront-mockup/shop.js (no browser, no server) on JSON cases from stdin.
// argv[2] = path to shop.js. Cases: {fn:'constants'} | {fn:'pacificDay',iso} | {fn:'selectionLine'|'availabilityWord',args}
// | {fn:'refresh',catalog,freshness,note,now}. Prints one JSON array of results.
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[2], 'utf8');
const block = /\/\/ FRESHNESS-BEGIN\n([\s\S]*?)\/\/ FRESHNESS-END/.exec(source);
if (!block) throw new Error('shop.js has no FRESHNESS block');
const names = '{STALE_AFTER_DAYS,AVAILABILITY_WORDS,pacificDay,selectionLine,availabilityWord,refreshFreshness}';
const cases = JSON.parse(fs.readFileSync(0, 'utf8'));
const results = cases.map(c => {
  const note = c.note ? {dataset: {checkedOn: c.note.checkedOn, phone: c.note.phone}, textContent: c.note.text} : null;
  const ctx = vm.createContext({catalog: c.catalog || [], catalogFreshness: c.freshness, document: {querySelector: () => note}});
  const f = vm.runInContext(`${block[1]}\n(${names})`, ctx);
  switch (c.fn) {
    case 'constants': return {stale: f.STALE_AFTER_DAYS, words: JSON.parse(JSON.stringify(f.AVAILABILITY_WORDS))};
    case 'pacificDay': return f.pacificDay(new Date(c.iso));
    case 'selectionLine': return f.selectionLine(...c.args);
    case 'availabilityWord': return f.availabilityWord(...c.args);
    case 'refresh':
      f.refreshFreshness(new Date(c.now));
      return {availability: ctx.catalog.map(p => p.availability === undefined ? null : p.availability), note: note && note.textContent};
    default: throw new Error('unknown case ' + c.fn);
  }
});
console.log(JSON.stringify(results));
