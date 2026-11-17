"""Product-only label provenance and phrase filtering; never an exemption for money/contact.

A label read is private evidence, not a verified health/origin claim. Its exact words
may be quoted, with source=label and the original photo bound into the draft hash.
"""
import json
import re

from hass import live_policy, media

FOOD_KINDS = frozenset({'origin/organic', 'health/awards/endorsements'})


def food(product):
    # Unknown/missing category stays conservative; only explicit non-food shelves opt out.
    return product.get('category') not in {'general', 'flowers', 'hardware'}


def label_text(details):
    return list(dict.fromkeys(v for key, value in details.items() if key not in {'category', 'barcode'}
                             for v in (value if isinstance(value, list) else [value]) if isinstance(v, str) and v))


def remember(root, sha, details):
    """Write-once label-read receipt beside the original, never inside the website."""
    folder = media._open_root(root) / 'labels'
    media._private_dir(folder)
    path = folder / (sha + '.json')
    if media._existing(path) is None:
        media._write_new(path, json.dumps({'source': 'label', 'photo': sha, 'text': label_text(details)},
                                        sort_keys=True).encode() + b'\n')


def source(root, sha, text):
    """Revalidate the admitted photo read at prepare/apply, not an interpreter's assertion."""
    if not root or not isinstance(sha, str) or not media.SHA_RE.fullmatch(sha) or not isinstance(text, list) or not text or len(text) > 100:
        return None
    folder = media._open_root(root) / 'labels'
    media._private_dir(folder)
    raw = media._existing(folder / (sha + '.json'))
    try:
        receipt = json.loads(raw) if raw and len(raw) <= media.SIDECAR_MAX else {}
    except ValueError:
        return None
    if receipt.get('source') != 'label' or receipt.get('photo') != sha or any(t not in receipt.get('text', []) for t in text):
        return None
    return {'source': 'label', 'photo': sha, 'text': text}


def valid_source(value):
    return (isinstance(value, dict) and set(value) == {'source', 'photo', 'text'} and value['source'] == 'label'
            and isinstance(value['photo'], str) and bool(media.SHA_RE.fullmatch(value['photo']))
            and isinstance(value['text'], list) and 0 < len(value['text']) <= 100
            and all(isinstance(t, str) and 0 < len(t) <= 600 for t in value['text']))


def protected(text, product, names=()):
    """Screen exact label phrases independently; extra owner words remain screened."""
    evidence = product.get('labelSource')
    rest = text
    if isinstance(rest, str) and valid_source(evidence):
        for phrase in sorted(evidence['text'], key=len, reverse=True):
            # Label evidence never excuses contact, money, trail claims or hidden script.
            kinds = live_policy._protected(phrase)[1]
            if kinds - FOOD_KINDS - {live_policy.UNCHECKED} or live_policy._mixed_script(phrase):
                continue
            if food(product):
                # Food claims are attributed, never a bare assertion or badge.
                rest = re.sub(r'Label says:\s*[“\"]' + re.escape(phrase) + r'[”\"]', '', rest, flags=re.I)
            else:
                rest = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', '', rest, flags=re.I)
    found, kinds = live_policy._protected(rest, 'products', names)
    if not food(product):
        kinds -= FOOD_KINDS
        # Preserve the sentence counter only when some still-protected kind remains.
        found = type(found)({s: n for s, n in found.items() if live_policy._protected(s)[1] - FOOD_KINDS})
    return found, kinds


def sanitize(slots, details):
    """Change the listing itself before drafting; preview and published bytes then agree."""
    text = label_text(details)
    evidence = {'source': 'label', 'photo': slots.get('photo'), 'text': text}
    product = {'category': slots.get('shelf'), 'labelSource': evidence}
    dropped = []
    for field in ('name', 'maker', 'description', 'image_alt'):
        value = slots.get(field)
        if not isinstance(value, str):
            continue
        value = re.sub(r'Label says:\s*“\s*”[.]?', '', value)
        if food(product):
            phrases = [t for t in text if live_policy._protected(t)[1] & (FOOD_KINDS | {live_policy.UNCHECKED})]
            for phrase in phrases:
                value = value.replace('Label says: “' + phrase + '”', phrase)
            if phrases:
                rx = re.compile('|'.join(re.escape(t) for t in sorted(phrases, key=len, reverse=True)))
                value = rx.sub(lambda m: 'Label says: “' + m[0] + '”', value)
        kept = []
        # Drop just the problematic clause, preserving neighbouring copy and sizes.
        for sentence in re.split(r'(?<=[.!?;])\s+|\n+', value):
            parts = re.split(r',\s+(?![^“]*”)|\s+and\s+(?![^“]*”)', sentence) if protected(sentence, product)[1] else [sentence]
            for part in parts:
                if protected(part, product)[1]:
                    dropped.append(part.strip())
                else:
                    kept.append(part)
        fallback = {'name': 'New item', 'maker': 'Producer not identified'}.get(field, slots.get('name') or 'New item')
        slots[field] = ' '.join(kept).strip() or fallback
    slots['intake']['dropped_claims'] = list(dict.fromkeys([*slots['intake'].get('dropped_claims', []), *dropped]))
    public = ' '.join(str(slots.get(k) or '') for k in ('name', 'maker', 'description', 'image_alt'))
    return [t for t in text if t in public]
