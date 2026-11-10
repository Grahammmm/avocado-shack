# Add a new item: `item.add`

Skill `item.add` (SKILLS-ITEMADD-1, card 14 of 20 in `reports/hass/SKILLS-SPEC.md`, row 3.1). Code: `hass/skills/item_add.py`.
Cases: `hass/tests/fixtures/skills/item_add/item.add.jsonl`. Tests: `hass/tests/test_skills_item_add.py`,
`hass/tests/test_undo_new_item.py`, plus the shared runners `test_skills_plans` and `test_skills_cases`.
Authoring rules for any skill: `docs/hass/SKILLS.md`. Wording: `docs/hass/VOICE.md` (every reply below follows it).

## What it does

Mike sends a photo and a few words ("new honey from Cal Poly, goes on the pantry shelf"). Hass drafts **one** change that adds
the product, the maker when the maker is new, the picture, and (once he says whether it is in) the stock word with today's
shelf check. He sees the draft and a preview and says `yes <code>`. Nothing is written before that yes. The editor, the claims
gate, the live boundary, the preview and the approval are the existing ones; the skill only plans typed ops.

## What Hass asks, in order (one short plain question per reply)

| Field | Slot | Filled how | Question when missing |
|---|---|---|---|
| name | `name` | his words; a price or size is taken out | "What is it called?" |
| packaged or fresh | `form` | `derive:form_guess`: a container word (jar, bottle, bag ...) means packaged; "fresh", "picked" means fresh; else the shelf | "Is it packaged or fresh?" |
| maker or farm | `maker` | his words; "same" / "same farm as last time" = the maker of the product added last; "don't know" = from the market | "Who grew these tomatoes?" (fresh) / "Who makes this lemon curd?" (packaged), plus "(Last time it was <Maker>. Say the name again to use them.)" when there is one; "same" without the name in his words is asked once more: "Please say the name, so I use the right one: <Maker>." (the claims gate wants a maker in his own words) |
| their town | `place` | `derive:saved_place` for a maker already on the site; only asked for a new maker | "Where is <Maker> based (town and state)?" |
| shelf | `shelf` | the shelf he named, else `derive:same_kind_majority` (where most products of the same kind sit) | "Which shelf does it go on: Dairy & cheese, Meat, Pantry, Drinks & coffee or Bread?" |
| description | `description` | `derive:house_description`: one line in the shop's voice from his words and the serving sentences already on the site (#504 engine). Machine-valid, **not accepted**: shown as "I set: the description to ..., and you can send a different one if you like." | never asked unless the draft cannot be made |
| picture caption | `image_alt` | `derive:alt_text`: the name, plus "in a jar" only when he said jar | never asked unless the draft cannot be made |
| in stock or not | `availability` | his words only ("got in" = yes, "only a few" = limited, "sold out" = no) | "Is it in stock right now?" |
| the photo | `photo` (attachment) | the sha256 of the stored original | "Send a photo of it." |
| story of a new maker | `story`, `maker_url` | his words, plus short sentences from the maker's own web page when he gives its address (`maker_url`); "skip" keeps only the D5 line | "What should we say about <Maker>? A sentence is enough." (asked once, only for a new maker with neither words nor an address; a page that cannot be read or has nothing usable: the reason, then the same question) |

Optional, never asked: `display_brand`.

A product his name and maker already have on the site (a twin) is named **before** anything else is asked:
"Rigatoni pasta is already on the site. Do you want to change it instead?" (a hidden twin: "... is on the site but hidden. Do you
want me to bring it back instead?"; a held twin is refused).

## The draft

* New maker: `maker.add` (with no story, the D5 one line "<Maker> is based in <place>."; with his words and/or the maker's page, that
  story, see "The maker's story" below) and the line "<Maker> is new on the site,
  so I'm adding them too." A maker already on the site: "<Maker> is already on the site, so I'm using them." A hidden maker is
  never used: "<Maker> is hidden. Do you want me to bring them back first?"
* `product.add{name, brand, category, description, producerKey, photo, imageAlt}`; an unknown maker gets the house words
  (brand "Producer not identified", the card says "From the market", no maker record) and the line "I couldn't tell who makes
  it, so the card says it is from the market."
* **D2:** today's shelf check not recorded yet: `store.confirm_selection{<word>: [<new id>]}` and its own line "This also records
  today as the day you checked the shelves." Already recorded today: `product.set_availability{id, available}`, no extra line.
* **D9:** a price or size is never written: "Left off: the price ($9) and the size (8oz), because the website shows no prices or
  sizes." A name that is still a number after that is asked again.
* Claims (organic, local, origins) pass only when he said them; the claims gate in the editor checks the draft again.
  **Live (HASS-LIVE-ADD-1, G 2026-11-09):** a new product may go live from chat, live class `chat-live`. `product.add` (with
  its own `photo` and `imageAlt`) and `maker.add` (the name and the town, never a link, and only together with a product that
  names that maker) are in `live_policy.LIVE`; the brand, the maker line, the maker's name and the town must be in his own
  words of this request (otherwise Hass asks and drafts nothing); every sentence gate, the 10-record limit and undo are
  unchanged. Changing an existing product's brand or maker, a maker's place or link stay private (D4).
  `product.set_photo` (HASS-LIVE-ADD-2) is also live: a picture of a stored photo, house style (`id`, `photo`,
  `imageAlt`), for a new or an existing product.
* **One photo, one product:** when his words ("add the lemon curd and the plum jam", a name that lists two products, `&`, `+`, or
  "both" beside an "and" in the name) put two products on the one photo, the skill itself asks "One photo can go on one product.
  Which one is this photo for?", whatever the interpreter returned. A single name with an "and" in it ("Salt and vinegar chips") is
  one product. His answer ends the question: a later message of his that names the one product the plan is for ("The lemon curd
  only, please") lets the plan go on, while an earlier two-product message is still kept, so a plan whose product he has not
  picked, or a later message that lists two again, asks again.
* **The house description is enforced, not only reported:** a description (his own, or the drafted one) with a digit or price, a
  hype word, `!` or `?`, a length outside the shop's measured 59 to 167 characters or a sentence count outside 2 to 3 is not
  drafted; he is asked: "That description won't match the others on the site: ... Could you send a different one?" A claim word
  he did not say is left to the claims gate, which asks him about it.
* **Preview:** the proposal screenshot is of the new product card (its picture and neighbours), also when a new maker is added
  with it (`preview.proposal_record`); the maker record comes first in the change only because the product needs it.
* **D6, the picture (HASS-LIVE-ADD-2):** `product.set_photo` is a live operation (`id`, `photo`, `imageAlt` only). With the house render on (`houseRender`, SKILLS-PIC-1), a photo the render cannot make house-style gets a
  kind retake line ("I couldn't separate the product from the background ... A new photo on a plain surface ... If this one is
  fine, just reply yes."); a small one: "This photo is small ...". With the render off (today), the photo goes on as sent and a photo
  that misses the house look gets "I'll use the photo as you took it, so it may look different from the other pictures ...". The
  advice is read-only (`hass/house_style.py`, `hass/newitem_render.py`); Mike may say yes knowingly. A photo the render refuses
  when the editor installs it (`photos.install` returns a `Retake`, a photo too big to open, ...) now reaches Mike in its own
  plain sentence ("Could you take it again on a plain surface ...", `conversation._plain`), not the generic "I couldn't make
  that change". Nothing is drafted and nothing is written. The host needs `houseRender: true` and the Pillow 12.0.0 python
  (`docs/hass/PILLOW-HOST.md`); `reports/hass/live-add-2/` is the rehearsal with the real render.

## The maker's story (HASS-LIVE-ADD-2 C, HASS-SEC-3)

Code: `hass/maker_site.py`. The conversation reads the page BEFORE it opens its write transaction (`Conversation._read_sites` ->
`maker_site.prefetch`); the plan only sees that result through `ctx.maker_page` (`maker_site.prefetched`) and never touches the
network (the test kit gives recorded pages, so no test touches the network).

* **A maker already on the site is reused**, with its story as it is.
* **A new maker:** his words (`story`) and a short story written from the maker's own page when he gave its address. With
  neither, ONE question ("What should we say about <Maker>? A sentence is enough."); "skip", "no story" and the like keep only
  the D5 line. Nothing is invented.
* **The polite read:** https only, a plain public name (no IP address in any spelling, no `[...]`, no trailing dot, no
  localhost or other local name, ASCII only, a real top-level name, no user name or port), the site's `robots.txt` obeyed
  (a disallow, 401 or 403 means the page is never requested: "That website asks programs not to read it, so I won't."), one
  request per site every 2 seconds, no cookies, no proxy. A redirect is followed by the reader itself, never by the HTTP
  library: same site only (with or without `www.`), at most 3, and every hop is held to the same rules as the first request
  (a public address, resolved and checked again when each connection is made, so a name that changes its answer cannot lead
  inside; IPv4-mapped, NAT64, 6to4, Teredo and IPv4-compatible addresses do not count as public; the `robots.txt` of the host it
  lands on; the 2-second gap).
* **Limits of the whole read (SEC-3 M2):** at most 8 seconds for everything (robots.txt, every hop, the gaps and the page; a
  gap is never waited past it, the name lookup gets only the time left, the body is read in 16 KB pieces and a watchdog shuts
  the connection at the deadline), at most 640 KB in all (600 KB for a page, 64 KB for a robots.txt) and at most 6 requests.
  A site that cannot be read, or not in time, is the plain line "I could not read their site; tell me about them in a
  sentence." (a robots refusal or a bad address keep their own sentence, then the same question), **unless he has already
  answered it**: once he has given his own words or said "skip", a website that cannot be read is left out, he is told so, and
  his answer (or just the town line) is used; the same question is not asked twice.
* **The story (SEC-3 H2):** no page sentence is ever used as it stands. Code takes at most three facts from page sentences that
  pass every rule and writes the story from them, in the house voice, at most 2 sentences: what they make ("<Maker> makes
  small-batch fruit jam and relish."), since which year ("<Maker> started in 2019.") or, without a year, the town **only when it
  is the town he confirmed** ("<Maker> is based in Morro Bay."). A page sentence is left out whole when it has a number (a year
  is fine), `!`, `?`, `;`, a quotation, a link or an e-mail, a hype word, anything the live gate calls a claim, a claim,
  contact, price, third-party or instruction word (organic, award, trusted, call, order, price, Hass, publish, ...), a
  capitalised name that is not the maker or the confirmed town (a shop, a store, another place), first-person talk past a
  leading We / Our, or a character that is not plain ASCII. The words he would publish are shown in the preview as **"The maker's
  own site says: <the story> (source: <address>, read on <day>). These words go on the website as their story only if you say
  yes to this change."** and go live only with his `yes <code>` to that exact draft; the draft's hash binds the text.
* **Source record:** the address, the day, the page sentences the facts came from and the story are kept privately with the
  draft (`maker-sources.jsonl`), taken from the drafting call itself (SEC-3 L3): the plan is never run again for it, so the record
  is always the read the draft was written from. The address is not put on the maker: the website-link field is protected and
  is not published.
* **Known limit:** a page "We make ..." is credited to whatever maker name he gave; he reads the story and the address before
  his yes.

## The live gate (HASS-LIVE-ADD-2 B)

With `liveSite` on, `ctx.live` is true and the skill judges the live gate itself, so a claim is dealt with in plain words
before the draft rather than caught later:

* a claim (`live_policy.PLAIN_KINDS`: where it comes from or organic, a health claim or an award, trail details, a price,
  contact details) in the **name, the maker's story or the picture caption** is refused: "I can't put <what> on the website
  from chat, so nothing changed. Send it again without that and I'll add the product." The refusal is a `policy` backlog row for
  Graham;
* a claim in **his own description** (or in the drafted one) is rewritten to the house draft without it, and the reply lists
  "Left off: your wording of the description, because it says ...". He can still send a different description before yes;
* the draft is one op list (`maker.add`, `product.add`, `product.set_photo` by way of the photo, the shelf check), all with
  arguments the live table allows.

## Undo

`undo` drafts a `history.revert` that needs its own yes. The product is hidden, not deleted; a maker the change added is hidden
with it; the picture file stays in the site folder, unused (the declared residue). **The stock word and its day go with the
product, and the shelf-check day goes back**, so a new item and today's shelf check undo together (`hass/ops/history.py`). Every
other record, the store and the site files come back exactly as they were. Undoing the newest of two new items leaves the first
one as it is; an item Mike edited after adding it is a conflict ("changed after"), never overwritten.

## How the plan sees the world (dispatcher interface)

Built on the SKILLS-FW-3 dispatcher (PR 526, merged) plus its three optional hooks (SKILLS-FW-3d, PR 544; this branch carries
that commit until it merges) and against the FW-2 router (PR 525, not merged; the real-dispatcher tests stub the router).

* `plan(slots, ctx)` is pure. `ctx.content`, `ctx.today`, `ctx.texts` (his joined texts) and `ctx.media_root` /
  `ctx.photo_bytes(sha)` are optional; `ctx.next_product_id` and `ctx.selection_checked_today` override what the content says.
* A plan that must stop raises `Refusal` (`.reply`, `.kind` "question" or "refuse").
* `question(slot, slots, ctx)` gives the dynamic question; `notes(name, slots, ctx)` gives the `say` / `set` / `warn` lines shown
  beside the draft.

With the FW-3d hooks the real dispatcher shows `Refusal.reply` (a `question` keeps the open request, so his short answer
continues it), calls `notes()` (shelf-check, "Left off" and picture lines, before his yes) and `question()` (the saved-farm
offer: "Last time it was Etto. Say the name again to use them."). "Same as last time" meets the claims gate, which wants the
maker named in his own words, so the offer asks him to say the name again. `hass/tests/test_item_add_dispatch.py` runs this
through the real Conversation and Dispatcher (a missing farm and a short answer, a new maker's town, the shelf-check line, a
bad photo warned before the yes, a bad description asked again); it is skipped on a tree without the hooks.

## Cases (`item.add.jsonl`)

30 rows: 24 conversation rows through the real Conversation and Editor and 6 plan rows. The first 20 are the ten spec sentences
(clean, misspelled, vague "add this", a photo with no words, twin, price and size, unknown maker, one question at a time, two
items on one photo, organic said), a photo with the name as its caption, same farm as last time, a hidden maker, and today's
check already recorded. The 10 `live2-*` rows (HASS-LIVE-ADD-2) are: a known maker with the real house render, a new maker with a
recorded web page, a new maker with no words and no address (asked, nothing invented), a page that cannot be read (asked), the same
page answered with his own words and with "skip" (not asked again, his words or just the town are used), a
photo the render cannot cut out (retake sentence, nothing drafted), a claim in his description (rewritten, "Left off"), and
organic and origin words in the name (refused with the plain reason). 14 rows end in an approved draft that is undone. They use
the synthetic photos of #504 (`reports/hass/newitem-1/synthetic/`) and recorded pages (`hass/tests/fixtures/maker_site/`).
More tests: `hass/tests/test_maker_site.py` (37: robots, address rules, redirects hop by hop, size cap, story rules, rate gap, record),
`hass/tests/test_maker_site_sec3.py` (28: the SEC-1 findings H2, L2, M2, L1, L3: facts not sentences, the labelled preview and
the yes, the whole-read deadline, bytes and requests, the read before the transaction, the address forms, the drafting call's
record) and
`hass/tests/test_live_add_photo_undo.py` (9: live `product.set_photo`, one undo hides the product and the new maker).

```
python3 hass/skills/testkit.py run hass/tests/fixtures/skills/item_add/item.add.jsonl
python3 -B -m unittest hass.tests.test_skills_item_add hass.tests.test_undo_new_item -v
```
