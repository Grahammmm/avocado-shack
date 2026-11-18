"""Cache-only local reports. No credential, model or transport access.

Pure report functions accept an identity-checked reads.Snapshot. Only explicit
links join till and site records; missing links are gaps, never guessed matches.
Files are private, atomic replacements; pruning touches only dated report files.
"""
import json
import os
import re
import stat
import tempfile
from datetime import date, timedelta
from pathlib import Path

from hass.clover import cache, reads
from hass.clover.mapper import format_quantity, norm_name

KINDS = ("stock", "mismatch")
DATED = re.compile(r"(\d{4}-\d{2}-\d{2})-(stock|mismatch)\.md")


def low_stock(snapshot, threshold=5):
    """Sold out (including negative counts), positive low counts, and unknowns."""
    return {"kind": "stock", "as_of": snapshot.fetched_at, "sections": {
        "Sold out": [i for i in snapshot.items if i.stock is not None and i.stock <= 0],
        f"Low stock (at or under {threshold})": [i for i in snapshot.items if i.stock is not None and 0 < i.stock <= threshold],
        "No count": [i for i in snapshot.items if i.stock is None],
    }}


def till_vs_site(snapshot, content, links):
    """Compare active site products to explicit {productId: {cloverId, sku}} links.

    Hidden/held site products are not on the site. Till items (even hidden ones)
    stay in the comparison. No link is not proof an item is absent: label it so.
    """
    products = content["products"]
    if not isinstance(products, list) or not isinstance(links, dict):
        raise ValueError("report inputs")
    site = {p["id"]: p for p in products if p.get("status") == "active"}
    till = {i.id: i for i in snapshot.items}
    sections = {k: [] for k in ("Till items without a site link", "Site items without a till link", "Different names",
                               "Broken links", "Stock word disagreements")}
    joined_site, joined_till = set(), set()
    for pid, link in sorted(links.items()):
        if not isinstance(link, dict) or not isinstance(link.get("cloverId"), str):
            sections["Broken links"].append(f"{pid}: missing till id")
            continue
        cid = link["cloverId"]
        if pid not in site or cid not in till:
            sections["Broken links"].append(f"{pid} / {cid}: site item is absent or not active" if pid not in site else
                                             f"{pid} / {cid}: till item is absent")
            continue
        p, i = site[pid], till[cid]
        joined_site.add(pid)
        joined_till.add(cid)
        if link.get("sku") and link["sku"] != i.sku:
            sections["Broken links"].append(f"{pid} / {cid}: saved SKU differs from the till")
        if norm_name(p["name"]) != norm_name(i.name):
            sections["Different names"].append(f"{p['name']} / {i.name} ({pid} / {cid})")
        word = p.get("available")
        if i.stock is not None and (word in ("yes", "limited") and i.stock <= 0 or word == "no" and i.stock > 0):
            sections["Stock word disagreements"].append(f"{p['name']} ({pid}): site {word}; till {format_quantity(i.stock)}")
    sections["Till items without a site link"] = [f"{i.name} ({i.id})" for i in snapshot.items if i.id not in joined_till]
    sections["Site items without a till link"] = [f"{p['name']} ({pid})" for pid, p in sorted(site.items()) if pid not in joined_site]
    return {"kind": "mismatch", "as_of": snapshot.fetched_at, "sections": sections}


def _safe(text):
    # Render imported names as text, not Markdown/HTML or additional report lines.
    text = " ".join(str(text).split())
    return "".join("\\" + c if c in "\\`*_{}[]<>()#!|" else c for c in text)


def render_md(report, now, reachable=True):
    state, _ = reads.freshness(reads.Snapshot((), report["as_of"]), now, reachable)
    title = "Low stock" if report["kind"] == "stock" else "Till versus site"
    lines = [f"# {title}", "", f"Last sync: {report['as_of'].isoformat()}", f"Snapshot: {state}",
             "Comparison uses saved links only; unlinked items are gaps, not confirmed absences.", ""]
    for heading, rows in report["sections"].items():
        lines += [f"## {heading} ({len(rows)})", ""]
        for row in rows:
            if not isinstance(row, str):
                count = "no count" if row.stock is None else format_quantity(row.stock)
                row = f"{row.name} ({row.id}): {count}" + ("; hidden on till" if row.hidden else "")
            lines.append("- " + _safe(row))
        lines += ([] if rows else ["- None."]) + [""]
    return "\n".join(lines)


def _read_regular(path):
    """Open without blocking or following a link; only a regular file is read (a FIFO would hang open)."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        raise
    except OSError:
        raise cache.CacheUnsafe("products") from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise cache.CacheUnsafe("products")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            return handle.read().decode("utf-8")
    finally:
        os.close(fd)


def read_inputs(state, worktree):
    """Only local products + private links. An absent link table means no links."""
    content = json.loads(_read_regular(Path(worktree) / "hass/content/products.json"))
    folder = Path(state) / "clover"
    links = {}
    if cache._private_dir(folder, create=False):
        path = folder / "links.json"
        try:
            st = path.lstat()
        except FileNotFoundError:
            pass
        else:
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise cache.CacheUnsafe("links")
            links = json.loads(path.read_text("utf-8"))
    if not isinstance(links, dict):
        raise ValueError("links")
    return content, links


def headline(snapshot, content, links, now, threshold=5, reachable=True):
    """Counts only, never names, prices, paths, or arbitrary file text in chat."""
    state, label = reads.freshness(snapshot, now, reachable)
    if state == "too-old":
        return label
    stock = low_stock(snapshot, threshold)["sections"]
    sold, low, unknown = (len(rows) for rows in stock.values())
    differences = sum(len(rows) for rows in till_vs_site(snapshot, content, links)["sections"].values())
    body = (f"Till report: {sold} sold out, {low} running low, {unknown} with no count. "
            f"{differences} things to check between the till and the website. Nothing changed.")
    return reads._wrap(state, label, body)


def write_report(state, report, now, reachable=True, out=None):
    """Write one private file and prune only our stock/mismatch dates >=90 days old.

    Caller validates the state and refuses output inside the repository. Refuse
    symlink ancestors, unsafe folders/files, and hard-linked destination files.
    """
    if report["kind"] not in KINDS:
        raise ValueError("kind")
    root = Path(state) / "clover"
    cache._private_dir(root, create=True)
    folder = Path(out).absolute() if out is not None else root / "reports"
    for parent in (folder, *folder.parents):
        if parent.is_symlink():
            raise cache.CacheUnsafe("folder")
    cache._private_dir(folder, create=True)
    today = now.astimezone(reads.PACIFIC).date()
    target = folder / f"{today.isoformat()}-{report['kind']}.md"
    if target.exists() or target.is_symlink():
        st = target.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1:
            raise cache.CacheUnsafe("file")
    fd, tmp = tempfile.mkstemp(prefix=".report-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(render_md(report, now, reachable))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    for path in folder.iterdir():
        match = DATED.fullmatch(path.name)
        if not match:
            continue
        try:
            old = date.fromisoformat(match[1]) <= today - timedelta(days=90)
        except ValueError:
            continue
        st = path.lstat()
        if old and stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and st.st_nlink == 1:
            path.unlink()
    return target
