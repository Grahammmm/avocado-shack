// AV2152-12: measure the rendered text contrast of the published home (with its catalog) and /hike pages.
// Importable helpers (no browser or server when required); run directly by site-contrast-qa.py:
//   node storefront-mockup/site-contrast-qa.cjs --site-a DIR --site-b DIR      (QA_OUT_DIR outside the repo for output)
// It serves two folders written by sitegen.publish_files on 127.0.0.1, blocks every other host, answers /api and
// POST requests from fixtures only, and writes contrast.json. A contrast failure is a RESULT, not an error.
'use strict';
const fs = require('fs'), path = require('path'), http = require('http');

// ---------- colour maths (WCAG 2.2: sRGB linearisation with the 0.04045 breakpoint) ----------
const LIN = Array.from({ length: 256 }, (_, i) => { const c = i / 255; return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); });
const lum = ([r, g, b]) => 0.2126 * LIN[r] + 0.7152 * LIN[g] + 0.0722 * LIN[b];
const ratioOfLum = (a, b) => { const hi = Math.max(a, b), lo = Math.min(a, b); return (hi + 0.05) / (lo + 0.05); };
const contrastRatio = (a, b) => ratioOfLum(lum(a), lum(b));
const LARGE_PX = 18.666667;
const isLarge = (px, weight) => px >= 24 || (px >= LARGE_PX && Number(weight) >= 700);
const thresholdFor = (px, weight) => (isLarge(px, weight) ? 3 : 4.5);
const hex = c => '#' + c.map(v => v.toString(16).padStart(2, '0')).join('');

// Computed colours arrive as rgb()/rgba() or color(srgb r g b / a); returns [r,g,b,a] with 0..255 channels or null.
function parseColor(s) {
  s = String(s).trim();
  let m = /^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)$/.exec(s);
  if (m) return [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4]];
  m = /^color\(srgb\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)(?:\s*\/\s*([\d.]+%?))?\s*\)$/.exec(s);
  if (m) return [+m[1] * 255, +m[2] * 255, +m[3] * 255, m[4] === undefined ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : +m[4]];
  if (s === 'transparent') return [0, 0, 0, 0];
  return null;
}
// top over bottom (both [r,g,b,a]); channels stay unrounded until an opaque result is needed.
const over = (top, bottom) => {
  const a = top[3] + bottom[3] * (1 - top[3]);
  if (a === 0) return [0, 0, 0, 0];
  return [0, 1, 2].map(i => (top[i] * top[3] + bottom[i] * bottom[3] * (1 - top[3])) / a).concat(a);
};
const enc = c => c.slice(0, 3).map(v => Math.min(255, Math.max(0, Math.round(v))));
// layers bottom -> top, each [r,g,b,a, opacity]; the canvas is white. Returns an opaque [r,g,b] (rounded to bytes, as painted).
function backing(layers) {
  let c = [255, 255, 255, 1];
  for (const l of layers) c = over([l[0], l[1], l[2], l[3] * (l[4] === undefined ? 1 : l[4])], c);
  return enc(c);
}
function effectiveFg(fg, opacity, bg) { return enc(over([fg[0], fg[1], fg[2], fg[3] * opacity], [bg[0], bg[1], bg[2], 1])); }

// ---------- nearest passing foreground ----------
// Minimum squared distance in encoded RGB bytes, ties to the lowest numeric RGB, exact over all 16,777,216 colours:
// for a fixed (r,g) the feasible blue values are a union of intervals found by binary search (luminance is monotone in
// blue), and the closest feasible blue is the nearest interval end. Passing means ratio >= threshold against EVERY bg.
function nearestPassing(fg, bgs, thr) {
  const Ls = bgs.map(lum), n = Ls.length;
  const lumRG = (r, g) => 0.2126 * LIN[r] + 0.7152 * LIN[g];
  const okLight = (yrg, b, L) => { const Y = yrg + 0.0722 * LIN[b]; return Y >= L && ratioOfLum(Y, L) >= thr; };
  const okDark = (yrg, b, L) => { const Y = yrg + 0.0722 * LIN[b]; return Y <= L && ratioOfLum(Y, L) >= thr; };
  let best = null;
  for (let r = 0; r < 256; r++) for (let g = 0; g < 256; g++) {
    const yrg = lumRG(r, g);
    let set = [[0, 255]];
    for (let i = 0; i < n && set.length; i++) {
      const L = Ls[i];
      let lo = 0, hi = 256; // smallest blue satisfying the light side (256 = none)
      while (lo < hi) { const m = (lo + hi) >> 1; if (okLight(yrg, m, L)) hi = m; else lo = m + 1; }
      const lightMin = lo;
      lo = -1; hi = 255; // largest blue satisfying the dark side (-1 = none)
      while (lo < hi) { const m = (lo + hi + 1) >> 1; if (okDark(yrg, m, L)) lo = m; else hi = m - 1; }
      const darkMax = lo, next = [];
      for (const [a, b] of set) {
        if (darkMax >= 0 && a <= darkMax) next.push([a, Math.min(b, darkMax)]);
        if (lightMin <= 255 && b >= lightMin) next.push([Math.max(a, lightMin), b]);
      }
      set = next.filter(([a, b]) => a <= b);
    }
    for (const [a, b] of set) {
      const bb = Math.min(b, Math.max(a, fg[2]));
      const d = (r - fg[0]) ** 2 + (g - fg[1]) ** 2 + (bb - fg[2]) ** 2, v = r * 65536 + g * 256 + bb;
      if (!best || d < best.d || (d === best.d && v < best.v)) best = { d, v, rgb: [r, g, bb] };
    }
  }
  return best && best.rgb;
}
// Reference for tests: scan every colour. Slow (seconds); only used to check nearestPassing.
function nearestExhaustive(fg, bgs, thr) {
  let best = null;
  for (let r = 0; r < 256; r++) for (let g = 0; g < 256; g++) for (let b = 0; b < 256; b++) {
    const d = (r - fg[0]) ** 2 + (g - fg[1]) ** 2 + (b - fg[2]) ** 2;
    if (best && d > best.d) continue;
    if (!bgs.every(bg => contrastRatio([r, g, b], bg) >= thr)) continue;
    const v = r * 65536 + g * 256 + b;
    if (!best || d < best.d || (d === best.d && v < best.v)) best = { d, v, rgb: [r, g, b] };
  }
  return best && best.rgb;
}
const nearCache = new Map();
function recommend(fg, bgs, thr) {
  // Passing against the lightest and the darkest backing passes against every colour in between (ratio is
  // quasi-convex in the backing luminance), so only the extremes are searched.
  const sorted = [...new Map(bgs.map(b => [hex(b), b])).values()].sort((a, b) => lum(a) - lum(b));
  const ext = sorted.length > 2 ? [sorted[0], sorted[sorted.length - 1]] : sorted;
  const key = hex(fg) + '|' + ext.map(hex).join(',') + '|' + thr;
  if (!nearCache.has(key)) nearCache.set(key, nearestPassing(fg, ext, thr));
  const rgb = nearCache.get(key);
  if (!rgb) return { ok: false, lightest: hex(sorted[sorted.length - 1]), darkest: hex(sorted[0]) };
  if (!sorted.every(bg => contrastRatio(rgb, bg) >= thr)) throw new Error('recommendation failed its own recheck');
  return { ok: true, color: hex(rgb), worst: Math.min(...sorted.map(bg => contrastRatio(rgb, bg))) };
}

// ---------- assessment ----------
// run: {fg:[r,g,b,a], opacity, layers, size, weight, pixels?:[[r,g,b],...] (image-backed), unsupported?:string}
function assess(run) {
  if (run.unsupported) return { status: 'unassessed', reason: run.unsupported };
  const thr = thresholdFor(run.size, run.weight);
  const bgs = run.pixels && run.pixels.length ? run.pixels : [backing(run.layers)];
  let worst = Infinity, worstBg = null, fgOut = null;
  for (const bg of bgs) {
    const f = effectiveFg(run.fg, run.opacity, bg), r = contrastRatio(f, bg);
    if (r < worst) { worst = r; worstBg = bg; fgOut = f; }
  }
  const sorted = [...bgs].sort((a, b) => lum(a) - lum(b));
  const out = { threshold: thr, ratio: worst, fg: hex(fgOut), bg: hex(worstBg), status: worst >= thr ? 'pass' : 'fail' };
  if (bgs.length > 1) { out.bgRange = [hex(sorted[0]), hex(sorted[sorted.length - 1])]; out.bgCount = bgs.length; }
  out.bgs = bgs.length > 1 ? [sorted[0], sorted[sorted.length - 1]].map(hex) : [hex(bgs[0])];
  return out;
}

// Group failing occurrences by selector + foreground + threshold; one recommendation per group, passing against every
// backing the selector was measured on (passing or failing occurrences alike) while the backing stays fixed.
function summarize(occurrences) {
  const counts = { pass: 0, fail: 0, exempt: 0, unassessed: 0 };
  for (const o of occurrences) counts[o.status]++;
  const byGroup = new Map(), backings = new Map();
  for (const o of occurrences) {
    if (o.status === 'pass' || o.status === 'fail') {
      const bk = o.gsel + '|' + o.threshold;
      if (!backings.has(bk)) backings.set(bk, new Set());
      for (const b of o.bgs) backings.get(bk).add(b);
    }
  }
  for (const o of occurrences) if (o.status === 'fail') {
    const k = [o.gsel, o.fg, o.bg, o.threshold, o.size, o.weight, o.kind, o.interaction].join('|');
    if (!byGroup.has(k)) byGroup.set(k, { gsel: o.gsel, kind: o.kind, interaction: o.interaction, fg: o.fg, bg: o.bg, bgs: o.bgs, bgRange: o.bgRange || null, threshold: o.threshold, size: o.size, weight: o.weight, ratio: o.ratio, count: 0, vps: new Set(), states: new Set(), first: o.sel, text: o.text });
    const g = byGroup.get(k); g.count++; g.vps.add(o.vp); g.states.add(o.state); g.ratio = Math.min(g.ratio, o.ratio);
  }
  const failures = [...byGroup.values()].map(g => {
    const all = [...backings.get(g.gsel + '|' + g.threshold)].map(h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)));
    const fg = [1, 3, 5].map(i => parseInt(g.fg.slice(i, i + 2), 16));
    return { ...g, vps: [...g.vps].sort(), states: [...g.states].sort(), rec: recommend(fg, all, g.threshold), recBackings: all.length };
  });
  return { counts, failures };
}

if (require.main !== module) { module.exports = { LIN, lum, contrastRatio, ratioOfLum, thresholdFor, isLarge, parseColor, over, backing, effectiveFg, hex, nearestPassing, nearestExhaustive, recommend, assess, summarize, LARGE_PX, pageCollect }; return; }

// =====================================================================================================
// Browser collector (only when run directly)
// =====================================================================================================
const { out } = require('./qa-env.cjs').qaEnv({ preview: false });
const args = process.argv.slice(2), arg = n => { const i = args.indexOf(n); return i >= 0 ? args[i + 1] : null; };
const dirs = { A: arg('--site-a'), B: arg('--site-b') };
const refuse = m => { process.stderr.write('site-contrast-qa refused: ' + m + '\n'); process.exit(2); };
const repo = fs.realpathSync(path.resolve(__dirname, '..'));
for (const k of ['A', 'B']) {
  if (!dirs[k]) refuse('pass --site-a and --site-b (folders written by sitegen publish_files)');
  dirs[k] = fs.realpathSync(dirs[k]);
  if (dirs[k] === repo || dirs[k].startsWith(repo + path.sep)) refuse('site folders must be outside the repository');
}
const VIEWPORTS = [{ name: '390', width: 390, height: 844 }, { name: '1440', width: 1440, height: 900 }];
const NOW = new Date('2026-11-05T20:00:00Z'); // 12:00 Pacific, before the 2026-11-08 sample invitation
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' };

function serve(root) {
  const server = http.createServer((req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') { res.writeHead(405); return res.end(); }
    const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname); let file = path.join(root, rel);
    if (!file.startsWith(root)) { res.writeHead(404); return res.end(); }
    try { if (fs.statSync(file).isDirectory()) file = path.join(file, 'index.html'); } catch {}
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404, { 'Content-Type': 'text/html' }); return res.end('<p>Not found</p>'); }
      res.writeHead(200, { 'Content-Type': TYPES[path.extname(file)] || 'application/octet-stream' }); res.end(data);
    });
  });
  return new Promise(ok => server.listen(0, '127.0.0.1', () => ok(server)));
}

// ---- in-page collector (serialised into the page) ----
function pageCollect(opts) {
  const rootEl = opts.rootMarked ? document.querySelector('[data-cqa-root]') : document.body;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE']);
  const segment = (e, nth) => { let s = e.tagName.toLowerCase(); if (e.id && !/\d{3,}/.test(e.id)) s += '#' + e.id; const c = [...e.classList].slice(0, 2); if (c.length) s += '.' + c.join('.'); if (nth) { const sib = e.parentElement ? [...e.parentElement.children] : []; s += ':nth-child(' + (sib.indexOf(e) + 1) + ')'; } return s; };
  const pathOf = (e, nth) => { const p = []; for (let x = e; x && x !== document.documentElement; x = x.parentElement) { p.unshift(segment(x, nth)); if (x.id && !nth) break; } return p.join(' > '); };
  const generic = e => { const p = pathOf(e, false).split(' > '); return p.slice(-4).join(' > '); };
  const full = e => pathOf(e, true).split(' > ').slice(-6).join(' > ');
  const chainOf = (e) => {
    const els = []; for (let x = e; x; x = x.parentElement) els.push(x); els.reverse(); // html .. e
    let op = 1; const layers = []; let image = null;
    for (const x of els) {
      const cs = getComputedStyle(x); op *= parseFloat(cs.opacity);
      layers.push({ color: cs.backgroundColor, op, image: cs.backgroundImage !== 'none' ? cs.backgroundImage.slice(0, 40) : null, el: x });
    }
    return { layers, op };
  };
  const results = [];
  const add = (el, kind, text, fgStr, fsEl, node) => {
    const cs = getComputedStyle(fsEl || el);
    const { layers, op } = chainOf(el);
    const rng = node ? (() => { const r = document.createRange(); r.selectNodeContents(node); return r.getBoundingClientRect(); })() : el.getBoundingClientRect();
    if (!(rng.width > 0 && rng.height > 0)) return;
    const rec = { sel: full(el), gsel: generic(el), kind, text: text.trim().replace(/\s+/g, ' ').slice(0, 40), fgStr, opacity: op, size: parseFloat(cs.fontSize), weight: cs.fontWeight, rect: [rng.left + scrollX, rng.top + scrollY, rng.width, rng.height], layersRaw: [] };
    const disabled = el.closest('button:disabled,input:disabled,select:disabled,textarea:disabled,fieldset:disabled');
    if (disabled && (el === disabled || kind !== 'text' || disabled.contains(el))) rec.exempt = 'inactive (disabled) control: WCAG 1.4.3 exempts inactive user-interface components';
    if (rng.width <= 2 || rng.height <= 2) rec.exempt = rec.exempt || 'visually hidden (clipped to about 1 px), not rendered text';
    // Walk up until an opaque layer; any background image or overlapping non-ancestor box is "image-backed".
    let stopped = null, imageBacked = null;
    for (let i = layers.length - 1; i >= 0; i--) {
      const L = layers[i]; rec.layersRaw.unshift([L.color, L.op]);
      if (L.image) imageBacked = 'background-image ' + L.image;
      const m = /rgba?\(([^)]*)\)/.exec(L.color); const a = m ? (m[1].split(/[ ,/]+/)[3] === undefined ? 1 : parseFloat(m[1].split(/[ ,/]+/)[3])) : (L.color.startsWith('color(') ? 1 : 0);
      if (a * L.op >= 1 && L.color !== 'rgba(0, 0, 0, 0)') { stopped = L.el; break; }
    }
    if (!rec.exempt) {
      const cx = [0.1, 0.5, 0.9], hits = new Set(); let needsScroll = false;
      // elementsFromPoint only sees the viewport: an offscreen point is brought into view first (scroll restored afterwards).
      const rectNow = () => node ? (() => { const r = document.createRange(); r.selectNodeContents(node); return r.getBoundingClientRect(); })() : el.getBoundingClientRect();
      // A point is displayed only inside the browser viewport AND inside every overflow-clipping ancestor's box
      // (a text run scrolled out of an overflow:auto/hidden container is invisible to elementsFromPoint even when its viewport coordinates are on screen).
      const clippers = []; for (let c = el.parentElement; c; c = c.parentElement) { const s = getComputedStyle(c); if (s.overflowX !== 'visible' || s.overflowY !== 'visible') clippers.push([c, s.overflowX !== 'visible', s.overflowY !== 'visible']); }
      const inView = (x, y) => {
        if (!(x >= 0 && y >= 0 && x <= innerWidth && y <= innerHeight)) return false;
        for (const [c, cx2, cy2] of clippers) { const b = c.getBoundingClientRect(); if (cx2 && (x < b.left || x > b.right)) return false; if (cy2 && (y < b.top || y > b.bottom)) return false; }
        return true;
      };
      // Every scroll position this sampling may change (window + each scrollable ancestor) is saved and put back before each
      // point, so all geometry is recomputed from the untouched layout and the page is left exactly as found.
      const saved = [[null, scrollX, scrollY]]; for (let x = el.parentElement; x; x = x.parentElement) if (x.scrollLeft || x.scrollTop || x.scrollWidth > x.clientWidth || x.scrollHeight > x.clientHeight) saved.push([x, x.scrollLeft, x.scrollTop]);
      const restore = () => { for (const [x, l, t] of saved) { if (x) { if (x.scrollLeft !== l || x.scrollTop !== t) x.scrollTo({ left: l, top: t, behavior: 'instant' }); } else if (scrollX !== l || scrollY !== t) window.scrollTo({ left: l, top: t, behavior: 'instant' }); } };
      let sampled = 0;
      for (const fx of cx) for (const fy of [0.3, 0.7]) {
        restore();
        let r = rectNow(), x = r.left + r.width * fx, y = r.top + r.height * fy;
        if (!inView(x, y)) {
          // elementsFromPoint only sees the viewport: bring the point into view first.
          window.scrollTo({ left: Math.max(0, x + scrollX - innerWidth / 2), top: Math.max(0, y + scrollY - innerHeight / 2), behavior: 'instant' });
          r = rectNow(); x = r.left + r.width * fx; y = r.top + r.height * fy;
          if (!inView(x, y)) { // nested scroll container (e.g. a horizontally scrolling filter row): scroll the element itself
            el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            r = rectNow(); x = r.left + r.width * fx; y = r.top + r.height * fy;
          }
          if (!inView(x, y)) continue; // never displayable (off-canvas skip link, closed dialog parts): no backing to sample
          needsScroll = true;
        }
        sampled++;
        const stack = document.elementsFromPoint(x, y);
        // pointer-events:none text never appears in the stack: then every box found there is treated as beneath it.
        let seen = !stack.some(s => s === el || el.contains(s));
        for (const s of stack) {
          if (s === el || el.contains(s)) { seen = true; continue; }
          if (s.contains(el)) { if (s === stopped) break; continue; }
          const graphic = s instanceof SVGElement && !s.matches('text,tspan,svg') || ['IMG', 'CANVAS', 'VIDEO'].includes(s.tagName);
          if (!seen && !graphic) hits.add('covered by ' + segment(s, false)); else hits.add(segment(s, false));
          if (seen && stopped && s.contains(stopped)) break;
        }
      }
      restore();
      const covered = [...hits].find(h => h.startsWith('covered by'));
      if (covered) rec.unsupported = 'text overlapped by another box (' + covered + ')';
      else if (hits.size) imageBacked = (imageBacked ? imageBacked + '; ' : '') + 'overlapping ' + [...hits].slice(0, 2).join(', ');
      if (imageBacked) rec.imageBacked = imageBacked;
      if (imageBacked && needsScroll) { // the backing is only visible after scrolling: pixel capture repeats the scroll (see pageReveal)
        window.__cqaTag = (window.__cqaTag || 0) + 1; el.setAttribute('data-cqa-t', String(window.__cqaTag)); rec.tag = window.__cqaTag;
        rec.nodeIdx = node ? [...el.childNodes].indexOf(node) : -1;
      }
    }
    results.push(rec);
  };
  const visible = e => e.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true });
  const walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT);
  const seenEls = new Set();
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement; if (!el || SKIP.has(el.tagName) || !n.nodeValue.trim()) continue;
    if (!visible(el) || el.closest('[hidden]')) continue;
    const isSvg = el instanceof SVGElement;
    if (isSvg && !el.closest('text')) continue;
    const cs = getComputedStyle(el);
    if (isSvg) { if (cs.fill === 'none') continue; add(el.closest('text'), 'svg-text', n.nodeValue, cs.fill + '|' + cs.fillOpacity, el, n); continue; }
    if (el.tagName === 'OPTION') continue; // listed through the select's own value
    add(el, 'text', n.nodeValue, cs.color, el, n);
  }
  const scope = rootEl.querySelectorAll ? [...rootEl.querySelectorAll('*')].concat(opts.rootMarked ? [rootEl] : []) : [];
  for (const el of scope) {
    if (SKIP.has(el.tagName) || !visible(el) || el.closest('[hidden]') || el instanceof SVGElement) continue;
    if ((el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') && !['checkbox', 'radio', 'hidden', 'file', 'range', 'color'].includes(el.type)) {
      if (el.value) add(el, 'value', el.value, getComputedStyle(el).color, el, null);
      else if (el.placeholder) { const ps = getComputedStyle(el, '::placeholder'); add(el, 'placeholder', el.placeholder, ps.color, el, null); }
    }
    if (el.tagName === 'SELECT' && el.selectedOptions[0]) add(el, 'value', el.selectedOptions[0].text, getComputedStyle(el).color, el, null);
    for (const pseudo of ['::before', '::after']) {
      const ps = getComputedStyle(el, pseudo), c = ps.content;
      if (!c || c === 'none' || c === 'normal' || c === '""' || c === "''") continue;
      const txt = c.replace(/^["']|["']$/g, ''); if (!txt.trim() || ps.display === 'none') continue;
      const holder = { sel: full(el) + pseudo, gsel: generic(el) + pseudo };
      const before = results.length; add(el, 'pseudo', txt, ps.color, el, null);
      if (results.length > before) { const r = results[results.length - 1]; r.sel = holder.sel; r.gsel = holder.gsel; r.size = parseFloat(ps.fontSize); r.weight = ps.fontWeight; }
    }
  }
  return results;
}

// Scrolls a tagged element (window and nested containers) so it is displayed; returns its document rectangle and the undo data.
function pageReveal(a) {
  const el = document.querySelector('[data-cqa-t="' + a.tag + '"]'); if (!el) return null;
  const saved = [[null, scrollX, scrollY]]; for (let x = el.parentElement; x; x = x.parentElement) if (x.scrollWidth > x.clientWidth || x.scrollHeight > x.clientHeight) saved.push([x, x.scrollLeft, x.scrollTop]);
  window.__cqaUndo = saved;
  el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
  const n = a.nodeIdx >= 0 ? el.childNodes[a.nodeIdx] : null;
  let r; if (n) { const g = document.createRange(); g.selectNodeContents(n); r = g.getBoundingClientRect(); } else r = el.getBoundingClientRect();
  return [r.left + scrollX, r.top + scrollY, r.width, r.height];
}
function pageUndoReveal(tag) {
  for (const [x, l, t] of (window.__cqaUndo || [])) { if (x) x.scrollTo({ left: l, top: t, behavior: 'instant' }); else window.scrollTo({ left: l, top: t, behavior: 'instant' }); }
  window.__cqaUndo = null; document.querySelector('[data-cqa-t="' + tag + '"]')?.removeAttribute('data-cqa-t');
}
function pageRequired(sels) {
  return sels.map(s => { const els = [...document.querySelectorAll(s)].filter(e => e.checkVisibility({ checkVisibilityCSS: true }) && ((e.innerText ?? e.textContent) || '').trim()); return [s, els.length]; });
}
function pagePixels(pair) {
  const load = b64 => new Promise(ok => { const img = new Image(); img.onload = () => { const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; const x = c.getContext('2d', { willReadFrequently: true }); x.drawImage(img, 0, 0); ok(x.getImageData(0, 0, c.width, c.height)); }; img.onerror = () => ok(null); img.src = 'data:image/png;base64,' + b64; });
  // Ink pixels = where the normal capture differs from the text-suppressed one (dilated by 1 px for anti-aliasing);
  // the backing is the suppressed capture there. No ink found: every pixel of the text bounds.
  return Promise.all([load(pair[0]), load(pair[1])]).then(([a, b]) => {
    if (!a || !b || a.width !== b.width || a.height !== b.height) return null;
    const w = a.width, h = a.height, ink = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) if (a.data[i * 4] !== b.data[i * 4] || a.data[i * 4 + 1] !== b.data[i * 4 + 1] || a.data[i * 4 + 2] !== b.data[i * 4 + 2]) ink[i] = 1;
    let any = false; for (let i = 0; i < w * h; i++) if (ink[i]) { any = true; break; }
    const set = new Set();
    for (let i = 0; i < w * h; i++) if (!any || ink[i]) set.add(b.data[i * 4] + ',' + b.data[i * 4 + 1] + ',' + b.data[i * 4 + 2]);
    return [...set];
  });
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const occurrences = [], stateLog = [], coverageErrors = [], blocked = [];

async function measure(page, st, extra = {}) {
  await page.evaluate(() => document.fonts.ready);
  let rootMarked = !!extra.rootMarked;
  if (st.rootSel) { await page.evaluate(sel => document.querySelector(sel).setAttribute('data-cqa-root', ''), st.rootSel); rootMarked = true; }
  let runs;
  try { runs = await page.evaluate(pageCollect, { rootMarked: rootMarked }); }
  finally { if (st.rootSel) await page.evaluate(() => document.querySelector('[data-cqa-root]')?.removeAttribute('data-cqa-root')); }
  let n = 0;
  for (const r of runs) {
    const base = { state: st.id, route: st.route, vp: st.vp, interaction: extra.interaction || 'default', sel: r.sel, gsel: r.gsel, kind: r.kind, text: r.text, size: r.size, weight: r.weight };
    if (r.exempt) { occurrences.push({ ...base, status: 'exempt', reason: r.exempt, threshold: thresholdFor(r.size, r.weight), bgs: [] }); n++; continue; }
    let fgStr = r.fgStr, svgOpacity = 1;
    if (r.kind === 'svg-text') { const [f, o] = fgStr.split('|'); fgStr = f; svgOpacity = parseFloat(o); }
    const fg = parseColor(fgStr);
    if (!fg) { occurrences.push({ ...base, status: 'unassessed', reason: 'unparsed colour ' + fgStr, threshold: thresholdFor(r.size, r.weight), bgs: [] }); n++; continue; }
    const layers = r.layersRaw.map(([c, op]) => { const p = parseColor(c) || [0, 0, 0, 0]; return [p[0], p[1], p[2], p[3], op]; });
    const run = { fg, opacity: r.opacity * svgOpacity, layers, size: r.size, weight: r.weight, unsupported: r.unsupported };
    let method = 'computed styles';
    if (r.imageBacked && !r.unsupported) {
      try {
        let [x, y, w, h] = r.rect;
        if (r.tag) { const rr = await page.evaluate(pageReveal, { tag: r.tag, nodeIdx: r.nodeIdx }); if (rr) [x, y, w, h] = rr; }
        await page.evaluate(() => { const s = document.createElement('style'); s.id = 'cqa-notext'; s.textContent = '*,*::before,*::after{color:transparent!important;-webkit-text-fill-color:transparent!important;caret-color:transparent!important}svg text,svg tspan{fill:transparent!important}'; document.head.append(s); });
        const clip = { x: Math.max(0, x - 2), y: Math.max(0, y - 2), width: Math.max(1, Math.ceil(w) + 4), height: Math.max(1, Math.ceil(h) + 4) };
        const hidden = await page.screenshot({ clip, fullPage: true, animations: 'disabled' });
        await page.evaluate(() => document.getElementById('cqa-notext')?.remove());
        const shown = await page.screenshot({ clip, fullPage: true, animations: 'disabled' });
        const px = await page.evaluate(pagePixels, [shown.toString('base64'), hidden.toString('base64')]);
        if (r.tag) await page.evaluate(pageUndoReveal, r.tag);
        if (!px || !px.length) run.unsupported = 'image-backed text: backing pixels could not be read';
        else { run.pixels = px.map(s => s.split(',').map(Number)); method = 'backing pixels under the text bounds, text suppressed (' + r.imageBacked + ')'; }
      } catch (e) { await page.evaluate(() => document.getElementById('cqa-notext')?.remove()).catch(() => {}); if (r.tag) await page.evaluate(pageUndoReveal, r.tag).catch(() => {}); run.unsupported = 'image-backed text: pixel measurement failed'; }
    }
    const a = assess(run);
    occurrences.push({ ...base, ...a, method, ...(a.status === 'unassessed' ? { bgs: [] } : {}) }); n++;
  }
  return n;
}
async function required(page, st) {
  if (!st.required) return;
  const seen = await page.evaluate(pageRequired, st.required);
  for (const [s, c] of seen) if (!c) coverageErrors.push(`${st.id} @${st.vp}: required selector ${s} has no visible text`);
  st.seen = seen;
}
async function interactions(page, st) {
  const kinds = await page.evaluate(() => {
    const seen = new Map();
    const q = [...document.querySelectorAll('a[href],button,summary,select,input:not([type=hidden]):not([type=checkbox]),textarea')].filter(e => e.checkVisibility({ checkVisibilityCSS: true }) && !e.disabled && e.getBoundingClientRect().width > 0);
    q.forEach((e, i) => { const k = e.tagName + '.' + [...e.classList].join('.') + '|' + (e.closest('dialog') ? 'dialog' : '') + '|' + (e.parentElement ? e.parentElement.tagName + '.' + [...e.parentElement.classList].join('.') : '') + '|' + (e.getAttribute('aria-pressed') || '') + (e.closest('nav,footer,.preview,.filters,.maker-story,.hero-copy,.hike-event,.trail-invitation,.past-hike,.community-newsletter,.hike-notify,.catalog-controls') ? (e.closest('nav,footer,.preview,.filters,.maker-story,.hero-copy,.hike-event,.trail-invitation,.past-hike,.community-newsletter,.hike-notify,.catalog-controls').className || e.closest('nav,footer').tagName) : ''); if (!seen.has(k)) seen.set(k, i); });
    return [...seen.values()].map(i => ({ i, g: q[i].tagName.toLowerCase() + '.' + [...q[i].classList].join('.') }));
  });
  const handles = await page.$$('a[href],button,summary,select,input:not([type=hidden]):not([type=checkbox]),textarea');
  const vis = [];
  for (const h of handles) if (await h.evaluate(e => e.checkVisibility({ checkVisibilityCSS: true }) && !e.disabled && e.getBoundingClientRect().width > 0)) vis.push(h);
  let done = 0;
  for (const k of kinds.slice(0, 60)) {
    const h = vis[k.i]; if (!h) continue;
    for (const mode of ['hover', 'focus']) {
      try {
        await h.evaluate(e => e.scrollIntoView({ block: 'center', inline: 'center' }));
        if (mode === 'hover') { const b = await h.boundingBox(); if (!b || b.x + b.width / 2 > page.viewportSize().width || b.x < 0) throw new Error('not reachable by the pointer: ' + k.g); await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await sleep(40); } else await h.evaluate(e => e.focus({ focusVisible: true, preventScroll: true }));
        await h.evaluate(e => e.setAttribute('data-cqa-root', ''));
        await measure(page, st, { rootMarked: true, interaction: mode });
        done++;
      } catch (e) { coverageErrors.push(`${st.id} @${st.vp}: ${mode} measurement failed: ${String(e.message).split('\n')[0].slice(0, 90)}`); }
      finally { await h.evaluate(e => { e.removeAttribute('data-cqa-root'); e.blur && e.blur(); }).catch(() => {}); await page.mouse.move(0, 0); }
    }
  }
  st.interactive = done;
}

// ---- fixtures ----
function fixtureEvents(ideas) {
  const base = { timezone: 'America/Los_Angeles', meetingPoint: 'Coon Creek parking lot', meetTime: '8:45 am', meetingAddress: 'End of Pecho Valley Road, Los Osos', walkTime: '9:00 am', returnTime: 'Around 12:30 pm', distance: '6.6 miles', difficulty: 'Moderate', duration: '3–4 hours', bring: 'Water, a wind layer and a snack.', accessNote: 'Fixture access note: check in with the trail attendant.', description: 'Fixture hike description.', rsvpEnabled: true };
  const ev = (id, title, status, startsAt, more) => ({ ...base, id, title, status, startsAt, confirmedGuests: 2, remaining: null, rsvpOpen: false, ...more });
  const trail = ideas.find(i => i.id === 'idea-point-buchon') ? 'idea-point-buchon' : (ideas[0] || {}).id;
  return [
    ev('fx-scheduled', 'Fixture scheduled hike', 'scheduled', '2026-12-06T09:00:00-08:00', { trailId: trail, rsvpOpen: true, remaining: 5, confirmedGuests: 3 }),
    ev('fx-one', 'Fixture one-place hike', 'scheduled', '2026-12-13T09:00:00-08:00', { rsvpOpen: true, remaining: 1, confirmedGuests: 1 }),
    ev('fx-uncapped', 'Fixture uncapped hike', 'scheduled', '2026-12-20T09:00:00-08:00', { rsvpOpen: true, remaining: null }),
    ev('fx-full', 'Fixture full hike', 'scheduled', '2026-12-27T09:00:00-08:00', { rsvpOpen: true, remaining: 0 }),
    ev('fx-closed', 'Fixture closed-RSVP hike', 'scheduled', '2027-01-03T09:00:00-08:00', { rsvpOpen: false }),
    ev('fx-cancelled', 'Fixture cancelled hike', 'cancelled', '2026-12-10T09:00:00-08:00', { rsvpOpen: true, remaining: 4 }),
    ev('fx-started', 'Fixture started-today hike', 'scheduled', '2026-11-05T07:00:00-08:00', { rsvpOpen: true, remaining: 3 }),
    ev('fx-done-1', 'Fixture completed hike', 'completed', '2026-10-04T09:00:00-07:00', { recap: 'Fixture recap: a good day on the trail.' }),
    ev('fx-done-2', 'Fixture second completed hike', 'completed', '2026-09-06T09:00:00-07:00', { description: 'Fixture description only.' })
  ];
}
const json = body => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });

async function newPage(browser, vp, siteBase, cfg) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, timezoneId: 'America/Los_Angeles', locale: 'en-US', reducedMotion: 'reduce', serviceWorkers: 'block' });
  await ctx.clock.setFixedTime(NOW);
  const gates = [];
  cfg.release = () => { while (gates.length) gates.pop()(); };
  await ctx.route('**/*', async route => {
    const u = new URL(route.request().url());
    if (u.protocol === 'data:' || u.protocol === 'about:') return route.continue();
    if (u.hostname !== '127.0.0.1') { blocked.push(u.hostname); return route.abort(); }
    const p = u.pathname, m = route.request().method();
    if (p.startsWith('/api/')) {
      if (cfg.api === 'none') return route.fulfill({ status: 404, contentType: 'text/html', body: '<p>no</p>' });
      if (m === 'GET' && p === '/api/community') return route.fulfill(json({ acceptsSubmissions: cfg.accepts !== false, clubName: 'North Coast Hiking Club', events: cfg.events || [], routeIdeas: cfg.ideas }));
      if (m === 'POST') {
        const mode = p.includes('rsvps') ? cfg.rsvp : cfg.subscribe;
        if (mode === 'hang') { await new Promise(r => gates.push(r)); return route.fulfill(json({ message: 'Fixture saved.' })); }
        if (mode === 'abort') return route.abort('failed');
        if (mode === 'error') return route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error: 'Fixture server error: please check the details and try again.' }) });
        return route.fulfill(json({ message: 'Fixture success: you are on the list.' }));
      }
      return route.fulfill({ status: 404, body: '' });
    }
    if (m === 'GET' && p === '/community.json' && cfg.staticEvents) return route.fulfill(json({ clubName: 'North Coast Hiking Club', events: cfg.staticEvents, routeIdeas: cfg.ideas }));
    if (m === 'GET' && p === '/community.json' && cfg.communityFail) return route.fulfill({ status: 404, contentType: 'text/html', body: '<p>no</p>' });
    if (m === 'GET' && p === '/hiking-preview.json' && cfg.noPreview) return route.fulfill(json({ enabled: false }));
    return route.continue();
  });
  const page = await ctx.newPage();
  page.on('pageerror', e => coverageErrors.push(`page error in ${cfg.id}: ${String(e.message).slice(0, 80)}`));
  return { ctx, page };
}

async function loadAllCards(page, expected) {
  for (let i = 0; i < 80; i++) {
    const n = await page.locator('#catalog-grid article').count();
    if (n >= expected) break;
    await page.evaluate(() => { const s = document.querySelector('#catalog-sentinel'); s && s.scrollIntoView(); });
    const more = page.locator('#more-products');
    if (await more.isVisible()) await more.click();
    await sleep(60);
  }
  const n = await page.locator('#catalog-grid article').count();
  if (n < expected) coverageErrors.push(`catalog: only ${n} of ${expected} cards loaded`);
  await page.evaluate(() => window.scrollTo(0, 0));
  return n;
}
const expandAll = page => page.evaluate(() => document.querySelectorAll('details').forEach(d => { d.open = true; }));

async function formCycle(page, st, spec, cfg) {
  // spec: {form, fill:[[selector,value]], submit, key}; modes: success, error, abort(unreachable), hang(saving)
  for (const [mode, label] of [['hang', 'saving'], ['ok', 'success'], ['error', 'server-error'], ['abort', 'unreachable']]) {
    cfg[spec.key] = mode;
    for (const [sel, v] of spec.fill) { const l = page.locator(sel); if (await l.isEnabled()) { if ((await l.evaluate(e => e.tagName)) === 'SELECT') await l.selectOption({ index: 0 }); else await l.fill(v); } }
    const status = page.locator(spec.form + ' .form-status');
    await page.locator(spec.form + ' button[type=submit]').click();
    if (mode === 'hang') { await status.filter({ hasText: 'Saving' }).waitFor(); }
    else await page.waitForFunction(s => { const t = document.querySelector(s).innerText.trim(); return t && !/Saving/.test(t); }, spec.form + ' .form-status');
    const sub = { ...st, id: st.id + '/' + label, required: [spec.form + ' .form-status'] };
    await measure(page, sub); await required(page, sub); stateLog.push(strip(sub));
    if (mode === 'hang') { cfg.release(); await page.waitForFunction(s => !/Saving/.test(document.querySelector(s).innerText), spec.form + ' .form-status'); }
  }
}
const strip = s => ({ id: s.id, route: s.route, vp: s.vp, required: (s.seen || []).map(([a, b]) => [a, b]), interactive: s.interactive || 0 });

async function run() {
  const servers = { A: await serve(dirs.A), B: await serve(dirs.B) };
  const base = k => `http://127.0.0.1:${servers[k].address().port}`;
  const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROMIUM_PATH || undefined });
  const version = browser.version();
  try {
    const ideas = JSON.parse(fs.readFileSync(path.join(dirs.A, 'community.json'), 'utf8')).routeIdeas;
    const catalogCount = Number(/\[/.test(fs.readFileSync(path.join(dirs.A, 'catalog-products.js'), 'utf8')) ? JSON.parse(fs.readFileSync(path.join(dirs.A, 'catalog-products.js'), 'utf8').replace(/^const catalog=/, '').split(';\nconst')[0]).length : 0);
    const events = fixtureEvents(ideas);
    for (const vp of VIEWPORTS) {
      const mk = (id, route, extra = {}) => ({ id, route, vp: vp.name, ...extra });
      const open = async (site, route, cfg, st) => { const c = await newPage(browser, vp, base(site), Object.assign(cfg, { ideas, id: st.id })); await c.page.goto(base(site) + route); await c.page.waitForLoadState('networkidle'); return c; };

      // ----- home: ordinary (static host: no club service, forms closed up front) -----
      {
        const st = mk('home-ordinary', '/', { required: ['.hero h1', '.hero-intro', '.catalog-note', '#catalog-count', '#catalog-grid .food-description', '#catalog-grid .origin-label', '#catalog-grid .food-badges span', '.maker-story summary', '.maker-story-content p', '.market-values h2', '.story .signature', '#community-newsletter .form-status', '#community-newsletter label', 'footer', '.skip-link', '.preview', '.topline'] });
        const c = await open('A', '/', { api: 'none' }, st); const page = c.page;
        await page.locator('#catalog-grid article').first().waitFor();
        await loadAllCards(page, catalogCount); await expandAll(page);
        await measure(page, st); await required(page, st);
        await interactions(page, st); stateLog.push(strip(st));
        // dialogs: privacy and one product detail
        const pst = mk('home-privacy-dialog', '/', { rootSel: 'dialog[open]', required: ['dialog[open] #dialog-content'] });
        await page.locator('[data-policy]').click(); await measure(page, pst); await required(page, pst); stateLog.push(strip(pst));
        await page.keyboard.press('Escape');
        // unmatched search
        const ust = mk('home-unmatched-search', '/', { required: ['#catalog-count'] });
        await page.locator('#product-search').fill('zzzzqx'); await sleep(300);
        await measure(page, ust); await required(page, ust); stateLog.push(strip(ust));
        await c.ctx.close();
      }
      // ----- home: live notice + availability (fixture copy of content) -----
      {
        const st = mk('home-notice-availability', '/', { required: ['.home-notice', '#catalog-grid .availability', '.avail-filter', '.selection-checked'] });
        const c = await open('B', '/', { api: 'none' }, st); const page = c.page;
        await page.locator('#catalog-grid article').first().waitFor();
        await measure(page, st); await required(page, st); stateLog.push(strip(st));
        await page.locator('#avail-filter').check(); await sleep(300);
        const fc = { ...st, id: 'home-notice-availability/filter-checked', required: ['#catalog-grid .availability'] };
        await measure(page, fc); await required(page, fc); stateLog.push(strip(fc));
        await c.ctx.close();
      }
      // ----- home newsletter against a fixture club service -----
      {
        const cfg = { api: 'live', events: [], accepts: true, subscribe: 'ok' };
        const st = mk('home-newsletter', '/', {});
        const c = await open('A', '/', cfg, st);
        await c.page.locator('#community-newsletter').scrollIntoViewIfNeeded();
        await formCycle(c.page, st, { form: '#community-newsletter', key: 'subscribe', fill: [['#newsletter-email', 'visitor@example.test']] }, cfg);
        await c.ctx.close();
      }
      // closed-service forced submit
      {
        const st = mk('home-newsletter/closed-service', '/', { required: ['#community-newsletter .form-status'] });
        const c = await open('A', '/', { api: 'none' }, st);
        await c.page.locator('#community-newsletter').evaluate(f => { f.querySelectorAll(':disabled').forEach(x => { x.disabled = false; }); f.noValidate = true; f.requestSubmit(); });
        await c.page.locator('#community-newsletter .form-status').filter({ hasText: 'nothing was sent' }).waitFor();
        await measure(c.page, st); await required(c.page, st); stateLog.push(strip(st)); await c.ctx.close();
      }
      // ----- /hike: sample invitation + archive, no events (static) -----
      {
        const st = mk('hike-sample', '/hike', { required: ['.sample-caption', '.trail-invitation-date', '.trail-invitation .label', '.trail-stats dt', '.trail-logistics dt', '.trail-photograph figcaption', '#history-context', '.trail-journal-entry h3', '#hike-updates .form-status', '[data-trail-explorer] .trail-endpoint-label', '.trail-access'] });
        const c = await open('A', '/hike', { api: 'none' }, st); const page = c.page;
        await page.locator('#upcoming-hikes article').first().waitFor();
        await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();
        await page.locator('[data-trail-explorer][data-ready=true]').waitFor({ timeout: 30000 });
        await sleep(300); await expandAll(page);
        await measure(page, st); await required(page, st);
        await interactions(page, st); stateLog.push(strip(st));
        // sample RSVP completion
        const rs = mk('hike-sample-rsvp-complete', '/hike', { required: ['#preview-hike-rsvp .form-status', '#preview-hike-rsvp select'] });
        await page.locator('#preview-rsvp-name').fill('Fixture Walker'); await page.locator('#preview-rsvp-email').fill('walker@example.test');
        await page.locator('#preview-hike-rsvp button[type=submit]').click();
        await page.locator('#preview-hike-rsvp .form-status').filter({ hasText: 'No details were saved' }).waitFor();
        await measure(page, rs); await required(page, rs); stateLog.push(strip(rs));
        // enlarged map dialog
        const ms = mk('hike-sample-map-dialog', '/hike', { rootSel: 'dialog[open]', required: ['dialog[open] .trail-endpoint-label', 'dialog[open] .trail-profile-svg .profile-axis'] });
        await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();
        const big = page.getByRole('button', { name: 'Enlarge map', exact: true });
        if (await big.count()) { await big.click(); await sleep(400); await measure(page, ms); await required(page, ms); stateLog.push(strip(ms)); } else coverageErrors.push(`hike-sample-map-dialog @${vp.name}: no Enlarge map button`);
        await c.ctx.close();
      }
      // hike-updates form (live service)
      {
        const cfg = { api: 'live', events: [], accepts: true, subscribe: 'ok', noPreview: true };
        const st = mk('hike-updates', '/hike', {});
        const c = await open('A', '/hike', cfg, st);
        await c.page.locator('#hike-updates').scrollIntoViewIfNeeded();
        await formCycle(c.page, st, { form: '#hike-updates', key: 'subscribe', fill: [['#hike-email', 'visitor@example.test']] }, cfg);
        await c.ctx.close();
      }
      // ----- /hike: no events and no samples; calendar failure -----
      {
        const st = mk('hike-no-events-no-samples', '/hike', { required: ['.hike-empty h2', '.hike-empty p', '.hike-empty .text-link', '.history-empty'] });
        const c = await open('A', '/hike', { api: 'none', noPreview: true }, st);
        await c.page.locator('.hike-empty').waitFor(); await measure(c.page, st); await required(c.page, st); stateLog.push(strip(st)); await c.ctx.close();
        const fs2 = mk('hike-calendar-failure', '/hike', { required: ['#upcoming-hikes p', '#past-hikes .club-small'] });
        const d = await open('A', '/hike', { api: 'none', communityFail: true, noPreview: true }, fs2);
        await d.page.locator('#upcoming-hikes').filter({ hasText: 'isn’t available' }).waitFor(); await measure(d.page, fs2); await required(d.page, fs2); stateLog.push(strip(fs2)); await d.ctx.close();
      }
      // ----- /hike: real events through the fixture club service -----
      {
        const cfg = { api: 'live', events, accepts: true, subscribe: 'ok', rsvp: 'ok', noPreview: true };
        const st = mk('hike-real-events', '/hike', { required: ['.hike-event .label', '.hike-date', '.hike-event h2', '.hike-attendance', '.hike-facts dt', '.hike-facts dd', '.hike-access', '.hike-route', '.hike-ics', '.hike-cancelled .club-small', '.hike-cancelled h2', '.hike-full', '.hike-event .club-small', '.hike-event .button', '.past-hike summary', '.past-hike time', '.past-hike p', '[data-trail-explorer] .trail-endpoint-label'] });
        const c = await open('A', '/hike', cfg, st); const page = c.page;
        await page.locator('#upcoming-hikes article').first().waitFor();
        await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();
        await page.locator('[data-trail-explorer][data-ready=true]').waitFor({ timeout: 30000 }).catch(() => coverageErrors.push(`hike-real-events @${vp.name}: trail map did not mount`));
        await sleep(300); await expandAll(page);
        await measure(page, st); await required(page, st);
        await interactions(page, st); stateLog.push(strip(st));
        // RSVP dialog and its statuses
        const rd = mk('hike-rsvp-dialog', '/hike', { rootSel: 'dialog[open]', required: ['dialog[open] #hike-rsvp label', 'dialog[open] .setup-note', 'dialog[open] .hike-facts dt'] });
        await page.locator('[data-rsvp="fx-scheduled"]').click(); await page.locator('#hike-rsvp').waitFor();
        await measure(page, rd); await required(page, rd); stateLog.push(strip(rd));
        await formCycle(page, mk('hike-rsvp', '/hike', { rootSel: 'dialog[open]' }), { form: '#hike-rsvp', key: 'rsvp', fill: [['#rsvp-name', 'Fixture Walker'], ['#rsvp-email', 'walker@example.test'], ['#rsvp-party', '1']] }, cfg);
        await c.ctx.close();
      }
      // static host with events: RSVP not available online
      {
        const st = mk('hike-static-events', '/hike', { required: ['.hike-event .club-small'] });
        const staticEvents = events.filter(e => e.status === 'scheduled').slice(0, 2).map(e => ({ ...e, confirmedGuests: undefined, remaining: undefined, rsvpOpen: undefined, staticSite: undefined }));
        const c = await open('A', '/hike', { api: 'none', staticEvents, noPreview: true }, st);
        await c.page.locator('#upcoming-hikes article').first().waitFor(); await measure(c.page, st); await required(c.page, st); stateLog.push(strip(st)); await c.ctx.close();
      }
      // /hike/ is the same page as /hike
      {
        const st = mk('hike-trailing-slash', '/hike/', { required: ['#hiking-heading'] });
        const c = await open('A', '/hike/', { api: 'none' }, st); await c.page.locator('#upcoming-hikes article').first().waitFor();
        const a = await c.page.evaluate(() => document.title + '|' + document.querySelectorAll('h1,h2,h3').length);
        const d = await c.ctx.newPage(); await d.goto(base('A') + '/hike'); await d.locator('#upcoming-hikes article').first().waitFor(); await d.waitForLoadState('networkidle'); await sleep(400);
        const b = await d.evaluate(() => document.title + '|' + document.querySelectorAll('h1,h2,h3').length);
        if (a !== b) coverageErrors.push(`/hike/ and /hike differ at ${vp.name}: ${a} vs ${b}`);
        await measure(c.page, st); await required(c.page, st); stateLog.push(strip(st)); await c.ctx.close();
      }
    }
  } finally {
    await browser.close().catch(() => {});
    for (const k of Object.keys(servers)) await new Promise(r => servers[k].close(r));
  }
  return version;
}
run().then(version => {
  const summary = summarize(occurrences);
  const states = {};
  for (const s of stateLog) { const k = s.id + '@' + s.vp; states[k] = s; }
  const doc = { browser: 'Chromium ' + version, viewports: VIEWPORTS.map(v => `${v.width}x${v.height}`), clock: NOW.toISOString(), blocked: [...new Set(blocked)].sort(), coverageErrors: [...new Set(coverageErrors)], states: Object.values(states), counts: summary.counts, failures: summary.failures, occurrences };
  const file = path.join(out, 'contrast.json'); fs.writeFileSync(file, JSON.stringify(doc));
  process.stdout.write('RESULT ' + file + '\n');
}).catch(e => { process.stderr.write('site-contrast-qa error: ' + (e && e.stack || e) + '\n'); process.exit(1); });
