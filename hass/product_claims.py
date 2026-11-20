"""Product-only label provenance and phrase filtering; never an exemption for money/contact.

A label read is private evidence, not a verified health/origin claim. Its exact words
may be quoted, with source=label and the original photo bound into the draft hash.
"""
import json
import hashlib
import re

from hass import live_policy, media


def drop_copy_claims(value, owner_words, evidence=()):
    """NPP: drop unsupported clauses before filling slots; return only safe owner-note labels.

    Evidence is inspected for omissions, not used to authorize a claim. The old draft
    gates still run on the rebuilt listing. Never echo an arbitrary removed span.
    """
    reasons = []
    owner = '\n'.join(map(live_policy.claims.fold, owner_words.splitlines()))

    def kept(text):
        kinds = live_policy._protected(text)[1]
        if 'health/awards/endorsements' in kinds:
            folded = live_policy.claims.fold(text)
            reasons.append(next((label for label in ('immune support', 'cures colds')
                                 if live_policy.claims._said(label, folded)), 'health or award wording'))
            return False
        if 'origin/organic' in kinds and not live_policy._owner_said(text, owner):
            reasons.append('unconfirmed origin or organic wording')
            return False
        return True

    parts = re.split(r'[,;\n]+|(?<=[.!?])\s+', value)
    clean = ' '.join(part.strip() for part in parts if part.strip() and kept(part))
    for text in evidence:
        kept(text)
    return clean, tuple(dict.fromkeys(reasons))

FOOD_KINDS = frozenset({'origin/organic', 'health/awards/endorsements'})


def food(product):
    # Food label wording is attributed; every category still screens unsupported claims.
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


def remember_owner(root, sha, texts):
    folder = media._open_root(root) / 'owner-claims'
    media._private_dir(folder)
    text = [t for t in texts if live_policy._protected(t)[1] & {'origin/organic'}]
    key = hashlib.sha256(json.dumps(text, sort_keys=True).encode()).hexdigest()
    path = folder / (sha + '-' + key + '.json')
    if media._existing(path) is None:
        media._write_new(path, json.dumps({'source': 'owner', 'photo': sha, 'text': text}, sort_keys=True).encode())
    return text


def source(root, sha, text, kind='label'):
    """Revalidate the admitted photo read at prepare/apply, not an interpreter's assertion."""
    if not root or not isinstance(sha, str) or not media.SHA_RE.fullmatch(sha) or not isinstance(text, list) or not text or len(text) > 100:
        return None
    folder = media._open_root(root) / ('labels' if kind == 'label' else 'owner-claims')
    media._private_dir(folder)
    suffix = '' if kind == 'label' else '-' + hashlib.sha256(json.dumps(text, sort_keys=True).encode()).hexdigest()
    raw = media._existing(folder / (sha + suffix + '.json'))
    try:
        receipt = json.loads(raw) if raw and len(raw) <= media.SIDECAR_MAX else {}
    except ValueError:
        return None
    if not isinstance(receipt, dict) or receipt.get('source') != kind or receipt.get('photo') != sha:
        return None
    lines = receipt.get('text')
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        return None
    if any(t not in lines for t in text):
        return None
    return {'source': kind, 'photo': sha, 'text': text}


def valid_source(value, kind='label'):
    return (isinstance(value, dict) and set(value) == {'source', 'photo', 'text'} and value['source'] == kind
            and isinstance(value['photo'], str) and bool(media.SHA_RE.fullmatch(value['photo']))
            and isinstance(value['text'], list) and 0 < len(value['text']) <= 100
            and all(isinstance(t, str) and 0 < len(t) <= 600 for t in value['text']))


def protected(text, product, names=()):
    """Screen exact label phrases independently; extra owner words remain screened."""
    evidence = product.get('labelSource')
    rest = text
    owner = product.get('ownerSource')
    if isinstance(rest, str) and valid_source(owner, 'owner'):
        lines = '\n'.join(live_policy.claims.fold(t) for t in owner['text'])
        for shown, sentence in live_policy._pieces(rest):
            kinds = live_policy._protected(shown)[1]
            if kinds and kinds <= {'origin/organic'} and live_policy._owner_said(sentence, lines):
                rest = rest.replace(shown, '')
        # A typed organic claim permits that same word, not a different source place.
        if live_policy._owner_said('organic', lines):
            rest = re.sub(r'(?<!\w)organic(?!\w)', '', rest, flags=re.I)
    if isinstance(rest, str) and valid_source(evidence):
        for phrase in sorted(evidence['text'], key=len, reverse=True):
            # Label evidence never excuses contact, money, trail claims or hidden script.
            kinds = live_policy._protected(phrase)[1]
            if kinds - FOOD_KINDS - {live_policy.UNCHECKED} or live_policy._mixed_script(phrase):
                continue
            if food(product):
                # Food claims are attributed, never a bare assertion or badge.
                rest = re.sub(r'Label says:\s*[“\"]' + re.escape(phrase) + r'[”\"]', '', rest)
            else:
                rest = re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', '', rest)
    return live_policy._protected(rest, 'products', names)


def sanitize(slots, details):
    """Change the listing itself before drafting; preview and published bytes then agree."""
    text = label_text(details)
    evidence = {'source': 'label', 'photo': slots.get('photo'), 'text': text}
    product = {'category': slots.get('shelf'), 'labelSource': evidence}
    owner = [t for t in slots.get('_owner_texts', []) if live_policy._protected(t)[1] & {'origin/organic'}]
    if owner:
        product['ownerSource'] = {'source': 'owner', 'photo': slots.get('photo') or '0' * 64, 'text': owner}
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
