"""H01 migration check: prove the canonical content preserves the migrated site.

    python3 hass/migration_check.py [--repo PATH]

Compares hass/content against the frozen hass/content/migration-baseline.json
(taken from the site files at the migration base commit) and fails if any
baseline listing, maker, source link or held exclusion has been lost:

  * every baseline listing id still exists as an active or hidden product
    ("remove" means hide; records are never deleted);
  * every baseline maker still exists with an https source link;
  * every baseline source URL (maker links, route-idea sources, hold source) is
    still recorded in the content;
  * held products stay held, keep their recorded reason/source, are absent from
    the generated catalog and still match storefront-mockup/held-products.json;
  * route ideas remain undated ideas and sample invitations never become events;
  * the generated site files equal the committed ones.

It also reports whether the generated files are still byte-identical to the
pre-migration files (true at migration; later approved edits may change them).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass.content_model import REPO_ROOT, ContentError, load_and_validate  # noqa: E402
from hass.sitegen import SITE_PREFIX, diff_paths, render  # noqa: E402


def run_checks(repo: Path) -> tuple[list[str], dict]:
    """Return (failures, report). No files are written."""
    repo = Path(repo)
    failures: list[str] = []
    baseline = json.loads((repo / "hass" / "content" / "migration-baseline.json").read_text("utf-8"))
    try:
        content = load_and_validate(repo / "hass" / "content", repo / "storefront-mockup")
    except ContentError as exc:
        return [f"content invalid: {p}" for p in exc.problems], {}
    files = render(content, repo / "hass" / "templates")

    by_id = {p["id"]: p for p in content.products}
    status_counts: dict[str, int] = {}
    for p in content.products:
        status_counts[p["status"]] = status_counts.get(p["status"], 0) + 1

    # Listings.
    base_ids = baseline["listings"]["ids"]
    if len(base_ids) != baseline["listings"]["count"] or len(set(base_ids)) != len(base_ids):
        failures.append("baseline listing ids are inconsistent")
    missing = [i for i in base_ids if i not in by_id]
    if missing:
        failures.append(f"{len(missing)} baseline listings deleted: {missing[:10]}")
    wrong = [i for i in base_ids if i in by_id and by_id[i]["status"] not in ("active", "hidden")]
    if wrong:
        failures.append(f"baseline listings no longer active/hidden: {wrong[:10]}")
    preserved = len(base_ids) - len(missing) - len(wrong)

    # Makers and sources.
    base_makers = baseline["makers"]["keys"]
    lost_makers = [k for k in base_makers if k not in content.makers]
    if lost_makers:
        failures.append(f"baseline makers deleted: {lost_makers}")
    recorded_urls = {m["url"] for m in content.makers.values()}
    recorded_urls |= {r["sourceUrl"] for r in content.community["routeIdeas"]}
    recorded_urls |= {p["hold"]["source"] for p in content.products if p["status"] == "held"}
    sources = baseline["sources"]
    base_urls = list(sources["makerUrls"].values()) + list(sources["routeIdeaSources"].values()) \
        + [sources["heldSource"]]
    lost_urls = [u for u in base_urls if u not in recorded_urls]
    if lost_urls:
        failures.append(f"baseline source links no longer recorded: {lost_urls}")
    idea_ids = {r["id"] for r in content.community["routeIdeas"]}
    lost_ideas = [i for i in sources["routeIdeaSources"] if i not in idea_ids]
    if lost_ideas:
        failures.append(f"baseline route ideas deleted: {lost_ideas}")

    # Held exclusions.
    held = baseline["held"]
    catalog_js = files[SITE_PREFIX + "catalog-products.js"].decode("utf-8")
    catalog_ids = {r["id"] for r in json.loads(catalog_js[len("const catalog="):].rstrip("\n").rstrip(";"))}
    held_file = json.loads((repo / "storefront-mockup" / "held-products.json").read_text("utf-8"))
    held_file_ids = sorted(p["id"] for p in held_file["products"])
    if held_file_ids != held["ids"] or held_file.get("reason") != held["reason"] \
            or held_file.get("source") != held["source"]:
        failures.append("storefront-mockup/held-products.json no longer matches the held baseline")
    for hid in held["ids"]:
        rec = by_id.get(hid)
        if rec is None or rec["status"] != "held":
            failures.append(f"held product {hid} is no longer held")
            continue
        if rec["hold"]["reason"] != held["reason"] or rec["hold"]["source"] != held["source"]:
            failures.append(f"held product {hid} lost its recorded reason/source")
        if hid in catalog_ids:
            failures.append(f"held product {hid} appears in the generated catalog")

    # Events vs samples.
    preview_path = repo / "storefront-mockup" / "hiking-preview.json"
    if preview_path.is_file():
        preview = json.loads(preview_path.read_text("utf-8"))
        sample_ids = {preview.get("upcoming", {}).get("id")} - {None}
        event_ids = {e["id"] for e in content.community["events"]}
        if sample_ids & event_ids:
            failures.append(f"sample invitation promoted to a real event: {sorted(sample_ids & event_ids)}")

    # Generated files vs repo and vs the pre-migration files.
    out_of_date = diff_paths(files, repo)
    if out_of_date:
        failures.append(f"committed site files differ from generated output: {out_of_date}")
    pre = baseline["siteFileSha256"]
    unchanged = sorted(rel for rel, data in files.items() if hashlib.sha256(data).hexdigest() == pre.get(rel))

    report = {
        "baseCommit": baseline["baseCommit"],
        "baselineListings": len(base_ids),
        "baselineListingsPreserved": preserved,
        "activeProducts": status_counts.get("active", 0),
        "hiddenProducts": status_counts.get("hidden", 0),
        "heldProducts": status_counts.get("held", 0),
        "baselineMakers": len(base_makers),
        "makers": len(content.makers),
        "baselineSourceLinks": len(base_urls),
        "sourceLinksPreserved": len(base_urls) - len(lost_urls),
        "catalogListings": len(catalog_ids),
        "heldExcluded": [h for h in held["ids"] if h not in catalog_ids],
        "realEvents": len(content.community["events"]),
        "routeIdeas": len(content.community["routeIdeas"]),
        "generatedFiles": len(files),
        "identicalToPreMigration": f"{len(unchanged)}/{len(pre)}",
    }
    return failures, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        failures, report = run_checks(args.repo.resolve())
    except (OSError, ValueError) as exc:
        print(f"migration_check: io error: {type(exc).__name__}", file=sys.stderr)
        return 2
    for key, value in report.items():
        print(f"{key}: {value}")
    if failures:
        print("MIGRATION CHECK FAILED:")
        for failure in failures:
            print("  " + failure)
        return 1
    print("migration check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
