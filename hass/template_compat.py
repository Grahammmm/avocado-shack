"""Pre-change content drafts stay applicable across template edits (AVO-SHOP-CLEAN-1).

content_revision() hashes hass/templates/index.html, so editing that template would stale every draft
prepared before it. For each known edit we keep the exact replaced span and both file digests; the editor
rebuilds the previous template bytes only when the current file matches the recorded digest, then derives
the previous revision. A draft whose base is neither the current nor such a recorded previous revision is
still stale, and apply still re-runs the operations and the post-checks.
"""
import hashlib

# (rel path, sha256 of the current file, sha256 of the previous file, current span, previous span)
TEMPLATE_EDITS = (
    ("hass/templates/index.html", 'c91ab5855c8ad9a5ecd13bdd2bfe7bf0ee881df5c2aa3c8c071afde84c62ee1f', 'bff5e3bb24b79b4c8b396f6360c645cb9969739b0822c5c93c681464f64acff2',
     'div class="catalog-controls"><label>Find something good<input type="search" id="product-search" placeholder="Food, producer, or town"></label><label>Meet a producer<select id="brand-filter"><option value="">All producers</option></select></label><button type="button" id="clear-filters" class="text-link" hidden>Clear filters</button></div>\n<div class="filters views" aria-label="Show"><button data-view="packaged" aria-pressed="true" class="selected">Packaged goods</button><button data-view="produce" aria-pressed="false">Fresh produce</button><button data-view="all" aria-pressed="false">All items</button></div>\n<div class="filters" aria-label="Food categories"><button data-filter="all" aria-pressed="true" class="selected">All shelves</button><button data-filter="fruit" aria-pressed="false" hidden>Fruit</button><button data-filter="vegetables" aria-pressed="false" hidden>Vegetables</button><button data-filter="dairy" aria-pressed="false">Dairy &amp; cheese</button><button data-filter="eggs" aria-pressed="false">Eggs</button><button data-filter="meat" aria-pressed="false">Meat</button><button data-filter="pantry" aria-pressed="false">Pantry</button><button data-filter="drinks" aria-pressed="false">Drinks &amp; coffee</button><button data-filter="bread" aria-pressed="false">Bread</button><button data-filter="flowers" aria-pressed="false" hidden',
     'p class="catalog-note">“Based in” names the town a producer or maker calls home. It isn’t a claim that every ingredient was grown there.</p>\n<p class="catalog-note">Our selection changes with the seasons and deliveries. Come into the Shack to see what’s fresh today.</p>\n<div class="catalog-controls"><label>Find something good<input type="search" id="product-search" placeholder="Food, producer, or town"></label><label>Meet a producer<select id="brand-filter"><option value="">All producers</option></select></label><button type="button" id="clear-filters" class="text-link" hidden>Clear filters</button></div>\n<div class="filters" aria-label="Food categories"><button data-filter="all" aria-pressed="true" class="selected">All shelves</button><button data-filter="fruit" aria-pressed="false">Fruit</button><button data-filter="vegetables" aria-pressed="false">Vegetables</button><button data-filter="dairy" aria-pressed="false">Dairy &amp; cheese</button><button data-filter="eggs" aria-pressed="false">Eggs</button><button data-filter="meat" aria-pressed="false">Meat</button><button data-filter="pantry" aria-pressed="false">Pantry</button><button data-filter="drinks" aria-pressed="false">Drinks &amp; coffee</button><button data-filter="bread" aria-pressed="false">Bread</button><button data-filter="flowers" aria-pressed="false"'),
)

def previous_bytes(rel: str, data: bytes):
    """The bytes this template had before its recorded edit, or None when data is not exactly the recorded file."""
    for path, new_sha, old_sha, new_span, old_span in TEMPLATE_EDITS:
        if path != rel or hashlib.sha256(data).hexdigest() != new_sha: continue
        old = data.replace(new_span.encode(), old_span.encode(), 1)
        if hashlib.sha256(old).hexdigest() == old_sha: return old
    return None
