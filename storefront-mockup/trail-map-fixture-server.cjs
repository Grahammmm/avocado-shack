// RF1345-13: request handler for the private trail-map QA fixture server (trail-map-retry-qa.cjs).
// Importing this module starts nothing, reads no environment and writes nothing.
// It serves the in-memory /fixture page and regular files whose RESOLVED path lies inside the
// supplied root; a file or directory symlink that leads outside the root gets the plain 404
// before any of its bytes are read. The root is a stable QA fixture tree, not attacker-writable
// storage, so this is not a general time-of-check/time-of-use defence.
'use strict';
const fs = require('fs'), path = require('path');
const types = {'.js': 'text/javascript; charset=utf-8', '.css': 'text/css', '.webp': 'image/webp', '.json': 'application/json'};

function createTrailFixtureHandler(root, fixtureHtml) {
  const dir = path.resolve(root);
  const real = fs.realpathSync(dir);
  if (!fs.statSync(real).isDirectory()) throw new Error('trail fixture root is not a directory');
  // Strict descendant of the canonical root, judged by path.relative: a sibling such as
  // "<root>-other" is outside even though its name starts with the root's name.
  const inside = p => { const r = path.relative(real, p); return r !== '' && r !== '..' && !r.startsWith('..' + path.sep) && !path.isAbsolute(r); };
  return (req, res) => {
    const notFound = () => { res.statusCode = 404; res.end('no'); };
    let u;
    try { u = new URL(req.url, 'http://x').pathname; } catch { return notFound(); }
    if (u === '/fixture') { res.setHeader('content-type', 'text/html'); return res.end(fixtureHtml); }
    const file = path.join(dir, path.normalize(u));
    if (!file.startsWith(dir + path.sep)) return notFound();  // early lexical guard only
    let body;
    try {
      const target = fs.realpathSync(file);  // follows every file and directory link
      if (!inside(target) || !fs.statSync(target).isFile()) return notFound();
      body = fs.readFileSync(target);
    } catch { return notFound(); }  // missing, dangling, cyclic or unreadable: no path disclosed
    res.setHeader('content-type', types[path.extname(file)] || 'application/octet-stream');
    res.end(body);
  };
}

module.exports = {createTrailFixtureHandler};
