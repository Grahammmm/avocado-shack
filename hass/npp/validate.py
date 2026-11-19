"""S7 checks on reviewed copy, exact draft records, OCR, and the rendered card."""
from dataclasses import dataclass
import re

from hass import claims, live_policy, publish_live
from hass.content_model import CATEGORIES, TEXT_LIMITS, valid_supplier
from hass.house_style import OWNER_IMAGE_RE
from hass.npp import private_numbers as numbers
from hass.npp.copy import words
from hass.ops.photos import MAX_ALT, _alt_problem

ORIGIN_UNKNOWN = 'Ask us about the source in store.'


def _spans(text, size):
    tokens = words(text)
    return {tuple(tokens[i:i + size]) for i in range(len(tokens) - size + 1)}


def _contact(text):
    normalized = claims.unhidden(text)
    return bool('/home/' in normalized.casefold() or live_policy.EMAIL.search(normalized)
                or any(rx.search(normalized) for rx in publish_live.PATTERNS.values()))


def field_problem(writer, key, text, permits, ctx):
    """Fixed verdicts suitable for a private receipt; no rejected text or amounts."""
    field = {'story': 'maker_story', 'imageAlt': 'image_alt'}.get(key, key)
    hard = writer.limits['limits'].get(field, {}).get('hard_max_chars')
    if hard is None:
        hard = TEXT_LIMITS['product'].get(key, MAX_ALT)
    if not text or len(text) > hard:
        return 'length'
    if key == 'description':
        rule = writer.limits['limits']['description']
        if not rule['sentences_min'] <= len(re.findall(r'[.!?](?=\s|$)', text)) <= rule['sentences_max']:
            return 'sentences'
    if _contact(text):
        return 'contact'
    if problem := numbers.problem(text, ctx.private, permitted=permits):
        return problem
    banned = writer.voice['banned_words']
    if key == 'description' and (ctx.kind == 'non-food' or ctx.category == 'flowers'):
        # The product identity is not a serving suggestion (e.g. a French Toast Candle).
        item = writer.bindings(ctx, key).get('item', ('', None))[0]
        prose = re.sub(r'(?<!\w)' + re.escape(item) + r'(?!\w)', '', text, flags=re.I) if item else text
        if any(numbers.literal_spans(prose, [term]) for term in writer.voice['non_food_banned_words']):
            return 'non-food-serving'
    if any(numbers.literal_spans(text, [term]) for term in banned):
        return 'hype'
    if 'health/awards/endorsements' in live_policy._protected(text)[1]:
        return 'unsupported-claim'
    # Only the exact typed slot value can excuse a shared four-word owner span.
    spans = _spans(text, 4) - {span for value, _ in writer.bindings(ctx, key).values() for span in _spans(value, 4)}
    if any(spans & _spans(turn, 4) for turn in ctx.owner_words.splitlines()):
        return 'owner-chatter'
    if key == 'description':
        ours = _spans(text, writer.spec['no_copying']['span_words'])
        if any(ours & _spans(other, 8) for other in ctx.other_descriptions):
            return 'copied-description'
    return None


def _flat(text):
    return ' '.join(text.split())


def dom_problem(nodes, price_index, price, name, approved=(), private=(), allowed=None, required=()):
    """`nodes` are visible DOM text fragments in order, with the exact price element identified.

    Keep numbers licensed in copy only in exact, already checked fields; no numeric-value
    allowlist. Pass only the numeric-bearing fields (name and/or story) as `approved`.
    When `allowed` is given, every other public fragment must equal one of those approved
    strings (whitespace-folded) and every `required` string must be rendered, so a swapped
    description or any extra claim fails even if it has no contact or number in it.
    """
    if not isinstance(nodes, (tuple, list)) or not all(isinstance(s, str) for s in nodes) or name not in nodes:
        return 'card-text'
    if type(price_index) is not int or not 0 <= price_index < len(nodes) or nodes[price_index] != '$' + price:
        return 'card-price'
    remaining = list(approved)
    for index, text in enumerate(nodes):
        if _contact(text):
            return 'card-contact'
        if index == price_index:
            continue
        if text in remaining:
            remaining.remove(text)
            continue
        if numbers.problem(text, private):
            return 'card-number'
    # Also inspect adjacent fragments for OCR-like/spoken splits of numbers and money.
    rest = ' '.join(text if i != price_index and text not in approved else ' ; ' for i, text in enumerate(nodes))
    if numbers.problem(rest, private):
        return 'card-number'
    if allowed is not None:
        shown = {_flat(text) for i, text in enumerate(nodes) if i != price_index}
        if any(text.strip() and _flat(text) not in allowed for i, text in enumerate(nodes) if i != price_index):
            return 'card-copy'
        if any(_flat(text) not in shown for text in required):
            return 'card-copy'
    return None


@dataclass(frozen=True)
class Verdict:
    problems: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def ok(self):
        return not self.problems


def listing(writer, ctx, copy, draft, *, finance, origin, makers, live_site, photo_sha,
            frozen_sha, rendered_sha, picture_read, card_nodes, price_index, label_words=()):
    """Check a fully assembled S7/S8 listing; this function cannot publish or send.

    `makers` is the existing catalog, `photo_sha` is the source photo and `frozen_sha`
    and `rendered_sha` are independent evidence from S6 and S8. G calls with the actual
    prepared draft and DOM text; never use the expected text in place of a capture.
    """
    problems, warnings = [], []
    if not finance.private <= ctx.private or not writer.conform(copy.text, copy.selections, ctx):
        problems.append('template-conformance')
    records = draft.get('records', ())
    products = [r for r in records if r.get('collection') == 'products']
    new_makers = [r for r in records if r.get('collection') == 'makers']
    if (len(products) != 1 or not isinstance(products[0].get('after'), dict) or len(new_makers) > 1
            or len(records) != len(products) + len(new_makers) or products[0].get('before') is not None
            or [op.get('op') for op in draft.get('ops', ())] != (['maker.add'] if new_makers else []) + ['product.add']):
        return Verdict(('listing-records',), ())
    product = products[0]['after']
    text = copy.text
    if (ctx.category not in CATEGORIES or product.get('category') != ctx.category
            or any(not text.get(key) or text[key] != product.get(key) for key in ('name', 'description', 'imageAlt'))):
        problems.append('listing-fields')
    known = makers or {}
    maker = known.get(product.get('producerKey'))
    if new_makers:
        row = new_makers[0]
        maker = row.get('after')
        if (not isinstance(maker, dict) or row.get('key') != product.get('producerKey') or row.get('before') is not None
                or (maker.get('story') or None) != text.get('story') or not (maker.get('story') or maker.get('url'))
                or maker.get('name') != ctx.maker_name or live_policy._town(maker.get('place')) != ctx.town):
            problems.append('maker-panel')
    elif text.get('story'):
        problems.append('maker-panel')
    maker = maker if isinstance(maker, dict) else {}
    supplier = product.get('supplier')
    wanted = f'From {supplier}' if supplier else f"Based in {maker['place']}" if maker.get('place') else ORIGIN_UNKNOWN
    if (origin != wanted or supplier and (not valid_supplier(supplier) or not live_policy._owner_said(supplier, '\n'.join(map(claims.fold, ctx.owner_words.splitlines()))))
            or not maker and product.get('producerKey')):
        problems.append('origin')
    brands = writer.bindings(ctx, 'name')
    for key in ('brand', 'displayBrand'):
        shown = product.get(key)
        if not shown and key == 'displayBrand':
            continue
        if shown not in (claims.PLACEHOLDER, 'From the market', brands.get('brand', (None,))[0]) or not shown:
            problems.append('brand')
    price = finance.selling_price
    if not price or not finance.price_span or product.get('sellingPrice') != price:
        problems.append('price-provenance')
    private = ctx.private | finance.private
    # Check record text, including non-template fields. The only number exceptions are
    # the conforming copy fields and sellingPrice, separately verified above.
    for key, value in {**product, 'origin': origin}.items():
        if key in {'id', 'image', 'sellingPrice', 'labelSource', 'ownerSource'}:
            continue
        if isinstance(value, str) and (_contact(value) or numbers.problem(value, private) and key not in {'name', 'description', 'imageAlt'}):
            problems.append('public-text')
    for key, value in maker.items():
        if key == 'story' and new_makers:
            continue  # conforming story, including a typed founded year
        if isinstance(value, str) and (_contact(value) or numbers.problem(value, private, digits_allowed=not new_makers and key == 'story')):
            problems.append('public-text')
    image, alt = product.get('image'), product.get('imageAlt')
    if (not isinstance(image, str) or not OWNER_IMAGE_RE.fullmatch(image)
            or not re.fullmatch(r'[0-9a-f]{64}', frozen_sha or '') or not re.fullmatch(r'[0-9a-f]{64}', photo_sha or '')
            or draft.get('assets', {}).get(image) != 'sha256:' + frozen_sha or frozen_sha != rendered_sha
            or not isinstance(alt, str) or '(illustration)' in alt.casefold() or _alt_problem(alt, photo_sha)):
        problems.append('picture-binding')
    if problem := numbers.picture_problem(picture_read, ctx.source_read, label_words, private):
        problems.append(problem)
    elif _contact(picture_read):
        problems.append('picture-contact')
    # The card may show only the validated copy, the checked brand/origin lines and the maker panel.
    # An existing maker's catalog name, place and story are not part of this copy: each is shown only when it
    # carries no protected claim (health/awards/endorsements, superlatives, ...). A new maker's story is text['story'].
    panel = [maker.get('name'), maker.get('place')]
    if not new_makers and not live_policy._protected(maker.get('story') or '')[1]:
        panel.append(maker.get('story'))
    shown_ok = {_flat(v) for v in (text.get('name'), text.get('description'), text.get('story'), product.get('displayBrand'), product.get('brand'), origin,
                                   *panel) if isinstance(v, str) and v.strip()}
    if price and (problem := dom_problem(card_nodes, price_index, price, text.get('name'),
                                        tuple(text[k] for k in ('name', 'story') if text.get(k)), private,
                                        allowed=shown_ok,
                                        required=tuple(text[k] for k in ('name', 'description', 'story') if text.get(k)))):
        problems.append(problem)
    if claims.unstated(draft, ctx.owner_words, makers):
        problems.append('existing-claims')
    if live_site:
        if live_policy.unsaid(draft, ctx.owner_words):
            problems.append('existing-identity')
        if live_policy.check(draft):
            problems.append('existing-live-policy')
    measured = {**text, 'brand': product.get('displayBrand') or product.get('brand') or '', 'origin': origin,
                'image_alt': alt or '', 'maker_story': text.get('story', ''), 'maker_name': maker.get('name', ''),
                'maker_place': maker.get('place', ''), 'maker_url': maker.get('url', '')}
    for key, stats in writer.limits['fields'].items():
        value = measured.get(key, '')
        if isinstance(value, str) and (len(value) > stats['chars']['p90'] or len(value.split()) > stats['words']['p90']):
            warnings.append(key + '-p90')
    return Verdict(tuple(dict.fromkeys(problems)), tuple(warnings))
