# Shop and page skills (SKILLS-SHOP-1)

Six skills for what the owner changes on the home page and in the shop details. Design and catalog:
`reports/hass/SKILLS-SPEC.md` (3.20 to 3.26). How a skill is built: `docs/hass/SKILLS.md`. The code is
`hass/skills/shop.py` (hours, notice, contact) and `hass/skills/pages.py` (home text, about text, home photo). The
refusal for an FAQ or a new page is `page.faq` in `hass/skills/backlog.py`; it is not repeated here.

The site is one home page and the hike page. There is no About page and no FAQ page. "About" is the "Come on in"
story on the home page; a maker's story belongs to the makers skills.

| Skill | What Mike says | What changes | Live class |
|---|---|---|---|
| `shop.hours` | "we're open till 7 on fridays now" | the opening hours | **private-only** |
| `shop.notice` | "put a notice up: closed Thursday" | the one dated notice at the top of the home page | **private-only** |
| `shop.contact` | "our new number is 805 555 0100" | the phone number, the street, the town | **private-only** |
| `page.home` | "change the headline to ..." | the two-line headline, the intro line | **private-only** |
| `page.about` | "change the about text to ..." | the "Come on in" story | **private-only** |
| `page.photo` | a photo and "use this for the home page" | the photo at the top of the home page | **private-only** |

All six draft first and wait for `yes <code>`. Undo is `undo` (a `history.revert` draft that needs its own yes). None of
them releases to the live site. A skill only plans the typed ops that already exist (`store.set_hours`,
`store.set_notice`, `store.clear_notice`, `store.set_phone`, `store.clear_phone`, `store.set_address`,
`store.set_headline`, `store.set_intro`, `store.set_story`, `store.set_home_image`, `store.clear_home_image`).

**Live class** is what `live_policy.check` says about the plan. Contact is `private-only` because `live_policy`
protects `store.set_phone`, `store.clear_phone` and `store.set_address`: chat can draft and preview it, but a live release
needs Graham. `hass/tests/test_skills_shop.py` runs the plans through the real editor and the real policy, so a change
that moves a class fails the build. A sentence in a notice, headline, intro or story that carries a phone number or a
claim word (origin, organic, award) is drafted from his own words but is protected at release.

## shop.hours

One slot: `hours`, the **whole** new list (1 to 7 lines, 60 characters each). The model proposes the list. Code checks:

* `hours-untouched-lines`: every day he did not name keeps exactly what the site says now. The check reads each line
  by day ("Monday–Friday 9am–6pm", "Closed Sunday", "Daily 10am–4pm"), so splitting a line is fine and changing an
  unnamed day is not. If a day he did not name would change, or would drop out, nothing is drafted and he is asked:
  "Do you want Saturday to stay 9am–5pm?" (`Sunday to stay closed`, `Monday to Thursday to stay 9am–6pm`). Days he names
  are read from his own words, joined across the open request: "fridays", "mon to sat", "weekdays", "every day".
  A line that names no day ("Open late on market nights") stays unless he rewrites the list around it.
* `hours-no-conflict`: one day with two different statements ("Mon to Sun 9 to 6 and Mon to Fri 8 to 5") is a question.
  Independent comma-separated schedules ("Monday 9am–6pm, Monday 10am–4pm") are checked separately too; commas in
  grouped days ("Mon, Tue & Wed 9am–5pm", "Closed Mon, Tue & Wed") still belong to the same statement. Stored wording stays as given.
* `not-already-true`: the same lines as now (spacing aside): "It already says that: Saturday 9am–5pm. Did you mean
  something else?" and nothing is drafted.
* `holiday-is-notice`: a closed day on a date or a holiday ("closed Thanksgiving", "closed November 12", "closed the
  12th", "closed 11/12", "closed 2026-11-12", "closed tomorrow", "closed this Thursday", "closed Thursday only") is a notice, so the hours are not changed and he is asked what the notice
  should say and until when. A date written into an hours line is caught too, even when his words are not at hand.
  Plain weekly words ("closed Sundays", "closed Thursdays from now on", "closed every Thursday") are still hours.
* `no-price`: a price or a deal in an hours line is refused.

An empty list is refused ("I can't take the hours off the site. What should they say?"). More than 7 lines, a line over
60 characters, or two lines that say the same thing are sent back with one plain sentence. Edits: `store.json` `hours`;
the home page. Undo restores only the hours.

Sentences: "we're open till 7 on fridays now" · "winter hours: 10 to 4 every day" · "chnage sat hours to 9 to 5" (already
true) · "update the hours" (asks) · "Friday till 7, Saturday 9 to 6, closed Sundays" · "open Mondays now, 9 to 3" · after
"Which days?": "weekdays 8 to 5" · "Mon to Sun 9 to 6 and Mon to Fri 8 to 5" (asks which) · "closed Thanksgiving" (a notice,
asks until what day) · "remove the hours" (refused).

## shop.notice

Slots: `clear` (take it down), `text` (3 letters to 160 characters, his words), `until` (a day). Asks: "What should the
notice say?" and "Until what day?". Checks:

* `notice-dates`: the last day is today up to 60 days ahead, Pacific. A day that has passed is asked again; more than 60
  days is refused with the limit.
* `no-price`: "20% off", "$3", "sale", "half price", "per lb" and the like are refused, and the caller writes the
  request down as a price request. A notice can still say "drop off your crates" or "parking is behind the store".
* `not-already-true`: the same words and the same last day.

Taking it down when none is up is refused. A second notice replaces the first. Edits: `store.json` `notice`; the home
page. Undo restores the earlier notice or none. Residue: after the last day the notice also disappears by itself in the
browser, with no change made.

Sentences: "put a notice up: we're closed Thanksgiving, back Friday" · "notise: closed fri for inventory" · "take down the
notice" · "tell people about the holiday" (asks) · "notice: closed Thursday. also hours Friday 10 to 4" (a notice and the
hours in one draft) · "new notice: parking is behind the store until Dec 1" · after "Until what day?": "the 28th" ·
"notice: all produce 20% off" (refused) · "notice until next year" (refused, 60 days) · "notice: call 805 555 0100 for
orders" (drafted; protected for a live release).

## shop.contact

Slots: `phone`, `clear` (take the phone off), `street_address`, `town`. Checks:

* `phone-ten-digits`: ten US digits. Spaces, dashes, dots, brackets and a leading 1 or +1 are removed. Seven digits
  ("555-0100") gets "I need the area code and seven more digits"; ten digits that cannot be a real number
  ("123-456-7890") gets "That doesn't look like a real US phone number".
* `not-already-true`: a phone, street or town the site already shows. A part that is already there is left out of the
  draft; if everything is already there, nothing is drafted. Taking the phone off is a change in itself, so "take the
  phone off, town Morro Bay" (the town unchanged) drafts only the phone removal.

A phone and "take it off" together is a question. Street and town are at most 80 characters and need letters. Edits:
`store.json` `phone`, `streetAddress`, `town`; the home page and, for the address, the hike page. Undo restores them.

Sentences: "our new number is 805-555-0100" · "chang the phoen to ..." · "take the phone number off the site" · "we
moved: 1023 Example Street, Morro Bay" · "update our address" (asks) · new phone and new street in one message · after "What
is the number?": "805 555 0100" · "phone 555-0100" (refused) · "the number is 123-456-7890" (refused) · "just fix the town
to Los Osos". The numbers in the tests are in the 555-01xx range, which is reserved for make-believe numbers.

## page.home

Slots: `headline` (two lines, 40 characters each, 2 letters each), `intro` (3 letters to 160 characters), `reset`
(`headline` or `intro`: the shop's own words come back). Checks: `headline-two-lines` (one line asks for the second:
"What should the second line say?"), `intro-text`, `no-price`, `claim-in-his-words`, `not-already-true`.

`claim-in-his-words`: a boast such as "best", "number one", "finest", "award-winning", "family-owned" or "since 2019" is
only used if he said that word himself (the whole word or phrase, not part of another word such as "bestow", and not
negated or taken away in the same sentence: "do not call us the best", "the best is not what we are" and "remove best from the headline" do not say "best"), otherwise he is asked what to say. Origin, organic and health words are not
repeated here; `hass/claims.py` already asks for those. Parts of a request that are already true are left out of the
draft. A reset writes the shipped words, because there is no "clear" op: the store file then holds the shipped text and
the page looks as before. Undoing the earlier change is the exact way back, and the skill says so.

Sentences: "change the headline to Fresh from the coast. Picked this week." · "intro: Good food brings people together." ·
"chang the intro to say wlecome neighbors" · "make the home page friendlier" (asks for the words, writes none) ·
"headline: A small market. Big flavor. and intro: Come by for lunch." · "put the old headline back" · after "What should the
second line say?": "Just come in" · "headline: Best produce in California" (only if he said "best") · "make the headline bigger
and red" (a design change, written down) · "intro: everything is $2" (refused).

## page.about

Slots: `story` (one paragraph, 20 letters to 400 characters, his words) and `reset` (the shipped story comes back).
Checks: `story-one-paragraph`, `no-price`, `claim-in-his-words`, `not-already-true`. A maker's about text is the makers
skill; when he says "about" with a maker's name that skill is the one to use.

Sentences: "change the about text to: Michael has been buying produce for 30 years and knows every grower" · "update our story, we've
been open since 2019" · "abuot us: we are a famly market" · "rewrite the about section" (asks) · "put the original story
back" · after "What should the story say?": "A market with a person behind it." · "story: ... intro: ..." (the story and the
intro in one draft) · "add an About page" (no such page: `page.faq` writes it down) · "our story: certified organic since
day one" (drafted from his words; protected for a live release) · "story over 600 characters" ("shorten it to 400").

## page.photo

Slots: `photo` (the photo he sent, filled from the message's attachment), `image_alt` (what it shows, his words), `clear`
(put the shop's own photo back). Asks: "Send me the photo you want on the home page." and "What does the photo show?".
`alt-says-what-it-shows`: a file or camera name ("IMG_1234", "photo", "Screenshot ...") or a text over 200 characters
is asked again, using the same rule the photo op uses. Putting the old photo back when none of his is set is refused.

D6: **the home photo is unchanged in v1.** The home photo is a wide picture with its own look; the house render is
measured for the square product box only. The skill keeps today's behaviour: the photo's metadata is removed and his
pixels are kept. There is no `picture-render` side effect. A sideways photo (a rotation tag) is refused by the photo
step when the draft is made, with the reply `media.REPLIES` gives for it.

Undo of a new photo shows the shop's own photo again. Residue: the photo file stays in the site folder with nothing
pointing at it (the editor never deletes). Undo of "put the old photo back" brings his photo back.

Sentences: "use this for the home page, it's the front of the shop" · "new hompage pic: the stand outside" · "put the old photo
back" · "make this the main picture" (asks: home page or a product) · photo first, then "the home page", then "the shop front
on a sunny morning" · a photo and "home photo is the shop front, and put up a notice that we're closed Thursday" (two skills in
one draft) · "use this for the home page and the lemons" (asks which) · "put the old photo back" with none of his set
(refused) · alt "IMG_1234" (refused: say what it shows) · a PNG with a rotation tag (refused).

## Tests

* `python3 hass/skills/testkit.py run hass/tests/fixtures/skills/shop/shop.hours.jsonl` (and the other five files under
  `shop/` and `pages/`) runs one skill: **plan rows** (slots in, exact ops out, with the saved hours and his words in
  `ctx`) and **case rows** (the real Conversation, Editor, sitegen and claims on a scratch worktree, exact content diff,
  nothing written before `yes`, undo back to the start).
* `python3 -B -m unittest hass.tests.test_skills_plans hass.tests.test_skills_cases hass.tests.test_skills_shop -v` is what CI
  runs. `test_skills_shop` adds the lint with the case files, every rule id as a named function, the hours rules on their
  own, the live class from the real policy, the home photo end to end with a stored photo (set, undo, put back, undo that),
  and plain words in every reply.
* A model-written text (a headline, an intro, a story) is machine-valid in these tests, never accepted: a person reads it
  in the acceptance report.
* Not covered by the kit yet: a case row with a photo. The kit has no media store, so `page.photo` has plan rows and
  refusal rows here, and `test_skills_shop.HomePhotoEndToEnd` runs the draft, apply and undo with a stored photo.

## What these skills assume about the other cards

Nothing here edits `conversation.py`, `interpreter_prompt.py` or the router. The skills work through the test kit today and
stay off in the live conversation (`skills.mode` is `ops-only`) until SKILLS-FW-2 and SKILLS-FW-3 are merged and the
operator turns it on.

1. **A plan can stop with a question or a refusal.** `hass.skills.shop.SkillStop` is a `ValueError` with `reply` (the
   owner's words), `kind` (`question`: the open request stays and his next message answers it; `refused`: it ends) and
   `reason` (a `Backlog` reason, `price` for a price). The test kit already shows `exc.reply` to the owner. SKILLS-FW-3's
   dispatcher turns any plan exception into its one generic "could not set that up" line, so until it shows `exc.reply`
   (and, for `refused`, writes the backlog row with `exc.reason`) Mike would get the generic line for these questions.
2. **What a plan reads** (all optional; a plan works with `ctx=None`): `ctx.content.store` (or `ctx.store`) for the saved
   record, `ctx.today` (a date or `YYYY-MM-DD`) or `ctx.now`, and `ctx.texts` (the owner's texts of the open request, which
   FW-3's `Ctx` sets). Without `texts` only the checks that need his own words are skipped (`hours-untouched-lines`,
   `holiday-is-notice`, `claim-in-his-words`); the structural checks always run.
3. **Rules are functions in each module** (`HOURS_CHECKS`, `NOTICE_CHECKS`, `CONTACT_CHECKS`, `HOME_CHECKS`,
   `ABOUT_CHECKS`, `PHOTO_CHECKS`: id to `fn(slots, texts, ctx)` returning a `SkillStop` or None) and run inside `plan`. They
   are not registered in the dispatcher's `RULES`, whose reply shape (an answer and a backlog reason) writes a backlog row,
   which is wrong for a question like "Do you want Saturday to stay 9am–5pm?". The dispatcher's own `no-price` rule (dollar signs, dollar words,
   "per lb") is narrower than these and runs first.
4. **Slot names are lower case** (`street_address`, `image_alt`), because the FW-1 lint refuses `streetAddress` and `imageAlt`.
   The plan maps them to the op arguments.
5. **`action: enum set|clear` is `clear: bool`** in `shop.notice`, and `text` and `until` are required `unless:clear`.
   FW-3's `if:<slot>` is a truthiness test, so an enum value `clear` would still count as "set" and ask for the words.
6. **Photo.** `photo` is a `from_attachment` slot: FW-3 fills it with the stored original's sha256, and the plan passes it
   as `photo=<sha>` to `store.set_home_image`.
7. **Spelling.** FW-3's owner-words check compares stemmed words exactly, so a typo he asked to have fixed ("famly" for
   "family") would be left off a story or intro and he is asked again. Safe, but a spelling-tolerant check would remove the
   extra question.
