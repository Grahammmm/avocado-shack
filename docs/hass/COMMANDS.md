# Hass commands (owner card)

These are the only messages Hass treats as commands. Send each one as the whole message. Capital letters in the command
do not matter (`YES A1B2` is the same as `yes a1b2`). Codes are the short codes Hass puts in its replies; `A1B2` below
is only a placeholder.

A trailing `.` or `!` is ignored for every command except `remember` and `forget` (`Status.` and `Memory.` work).
The two note commands are stricter:

- `remember <key>: <text>` saves the text exactly as sent, so its capitals and any final `.` or `!` are kept.
- `forget <key>` ignores a trailing `!` but not a `.`, because a key may contain `.`: `forget parking.` looks for a
  note called `parking.` and leaves the `parking` note alone. Send `forget parking` with no full stop.

A yes or no with its code works in either order and survives everyday phone typing: commas and other punctuation, emoji and the words please, thanks, thank you, ok and okay are ignored, so `Yes, a1b2`, `yes a1b2 thanks`, `A1B2 yes` and `no a1b2 please` act as `yes a1b2` and `no a1b2`. Any other word keeps its meaning: `yes but make it 10am` and `no, 5pm` are still change requests.

A question mark means a question, never an answer. `yes a1b2?`, `no a1b2?`, `a1b2 yes?`, `yes?`, `no?`, a waiting code on its own (`a1b2` or `a1b2?`) and similar forms apply nothing, cancel nothing, record no approval and make no interpreter call. Hass replies `Nothing was changed. To apply a1b2, reply yes a1b2; to cancel it, no a1b2.` (with no or an unknown code, it lists the waiting codes).

| Send | What happens | Example |
| --- | --- | --- |
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. The reply says the change is saved but not on the website yet, because copying it to the website is a separate step. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft or question; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`) | Cancels the waiting draft or question; nothing changes. | `no` |
| `history` | Lists the last five approved changes (approved (still being saved), applied, checked, failed or undone) with their codes and states, each with where it is now (on the website, not confirmed on the website, undone). | `history` |
| `history <words>` | Lists up to 10 approved changes (same states and line format as `history`, each with its code and where it is now), newest first, whose summary contains every word you send; capital letters and accents do not matter, and the words may come in any order. Only the summary is searched, across all approved history, so the code of an older change can be found for `undo <code>`. Send 1–60 characters; no match says so, and no words gets a usage reply. It changes nothing, expires nothing and works while paused. | `history opening hours` |
| `undo` | Drafts an undo of the most recent applied change; a bare undo skips undos and takes the change before. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `status` | Says whether changes are paused, lists waiting drafts and the last result, and upcoming hike seat totals, and the last shelf check (`Shelf check: <day>`, the same words as the morning report; after a week it adds that the site says call to confirm). With a daily limit set, it also shows `Interpreter today: N of CAP` (change requests read today). It also counts `Photos waiting for details: N` and, when any, `Photos still downloading: M` (`unavailable` if the inbox cannot be read). It changes nothing. | `Status.` |
| `did it work?` (or `did that work?`, `did my change work?`): the same as `status` | Answers "did my change work?" in its `Last change:` line: done and on the website now (with the time it was checked), saved but not confirmed on the website (and why; if copying it stopped part way some pages may already show it, so ask for help to copy it again), did not reach the website (the website is unchanged), or undone. It changes nothing. | `did it work?` |
| `stop changes` (or `stop`, `pause`, `pause changes`) | Stops any approval from applying and replies how many requests are waiting. Drafts can still be prepared; changes already on the website stay there. | `stop changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note. | `forget parking` |
| `memory` | Lists your saved notes (up to 20, `Saved (N):`), then your aliases apart under `Aliases (N):` (up to 20, then `... and N more`); notes and aliases are counted and capped separately. An alias line reads `green jam -> Linn's blueberry preserves (photo-product-001)` with the product or maker name as it is on the site now and its id, `[hidden]` for a hidden product or maker and `[held]` for a held product. An alias whose product or maker is gone says `no longer on the site - send forget alias.<name>`; an unreadable saved alias says to send the same forget; when the catalog cannot be read right now it says `target unavailable right now`, not deleted. It only reads: it changes nothing, does not expire drafts, and works while paused. | `memory` |
| `alias <name>: <id>` | Saves your own name for a product id or maker key that exists now, so a lookup of that name finds it, and a plain-word change request ("the green jam is sold out") can use it to pick that record. Only aliases whose record still exists, the newest 50, reach change requests; an alias never establishes a claim. Send `forget alias.<name with - for spaces>` to remove it and stop the hint. | `alias green jam: photo-product-001` |
| `cost <id>: <pack cost> for <units>` | Saves what you paid for one purchase of a product (it must exist now, any status), with today's Pacific date, as your private note `cost.<id>`; sending a new cost updates it and says what it was. A number that is out of range is named (`Not saved: units must be a finite whole number.`). The cost is never on the website, in a draft or in what is sent to the interpreter; `memory` shows it to you and `forget cost.<id>` removes it. `remember cost.<id>: ...` does not work, use this command. It changes no price and works while paused. | `cost photo-product-001: 24.00 for 12` |
| `find <words>` | Lists up to 10 matching products, makers, hikes and route ideas, with ids: products and makers whose name matches (your aliases too), then hikes (by start, with the Pacific weekday, date and time) and route ideas whose title contains every word, each with its status, hidden, cancelled and completed ones included. It changes nothing and works while paused. | `find lion's mane` |
| `show <code>` | Sends that draft again: a waiting draft's full proposal text and its preview screenshot, or an applied change's lines (with its commit) and its checked screenshot. An expired, cancelled or replaced draft is named as such. It changes nothing, expires nothing and works while paused. | `show A1B2` |
| `report` (or `morning report`) | Replies the morning shelf report from your last shelf check (Pacific today): when you last checked, counts of available, limited, sold out and not confirmed products, the limited and sold-out names, and hikes today or tomorrow. These are shelf checks, not stock counts. It then adds a `Waiting for you:` block: each draft waiting for your yes or for details (code and summary, the same lines as `status`) and `Photos waiting for details: N`, or `Waiting for you: nothing`. It changes nothing, expires nothing and works while paused. | `report` |
| `post <id>` | Replies a draft Instagram-style caption for that active product (its name, description and maker) with its site photo attached, then the photo description. Nothing is posted, scheduled or saved. A product that is unknown, not on the site or without a photo gets a plain-words reply. It changes nothing and works while paused. | `post photo-product-001` |
| `post hike <id>` | Replies a ready-to-copy announcement draft for that scheduled, upcoming hike (title, time, meeting point, route). Nothing is posted, scheduled or saved. A hike that is unknown, cancelled, already past or not scheduled gets a plain-words reply. It changes nothing and works while paused. | `post hike hike-2026-11-14-point-buchon` |
| `margin <pack cost> for <units> at <margin>%` (optional `shrink <S>%`) | Replies a suggested selling price for one purchase line, with each step of the arithmetic (cost per unit, cost per sellable unit after shrink, the price, the cent rounding and the margin it gives) and the note that it is a suggestion only. A `$` before the pack cost and spaces around the numbers are fine; without `shrink` it is 0%. A number that is out of range is named in the reply (`Not calculated: units must be 1 to 10000.`); a message that starts with `margin` but is not in this form gets the one-line form to send. It stores nothing, puts no price on the site, does not read a change request and works while paused. | `margin 24.00 for 12 at 35%` |
| `margin <id> at <margin>%` (optional `shrink <S>%`) | Uses the cost you saved with `cost` for that product: replies `Using cost from <date>: <pack cost> for <units>.` and then the same steps and suggestion-only note as the form above. With no saved cost it says `No cost saved for <id>; send cost <id>: <pack cost> for <units> first.`; a margin out of range is named. It stores nothing, drafts no price change and works while paused. | `margin photo-product-001 at 35%` |
| `hidden` | Lists the hidden products (`product <id>: <name>`, by id) then the hidden makers (`maker <key>: <name>`), up to 20 lines, then `… and N more.`, and says to send `restore <id>` to bring one back. Held products are never listed. It changes nothing and works while paused. | `hidden` |
| `listing <id>` | Replies what the saved content shows for one id from `find`, starting `Saved listing (not a live website check):`: a product (name, maker, shelf, the first 120 characters of the description, availability word, status), a maker (name, place, number of active products), a hike (Pacific weekday, date and time, status, meeting point, capacity) or a route idea (title, place, status); anything not saved reads `not set`. A hidden or held product says `not shown on site`. An unknown id, or one that matches more than one listing, says to send `find <words>`. The id must match exactly, capital letters included. It changes nothing and works while paused. | `listing Etto` |
| `help` (or `commands`, `?`) | Replies a short list of every command with one example each. It changes nothing. | `help` |

Saved notes never change the site, and pause does not affect them.

Photos: send one photo per message, as JPEG or PNG, up to 20 MB. A phone photo's rotation is kept, so it shows upright
(only that rotation tag is kept, never its location, camera or date); only a PNG with a rotation tag is refused. Any
other file, or a photo that is too large, incomplete or unreadable,
gets a reply naming the limit, and nothing is saved or drafted.

Any other message is read as a change request. Hass replies with a draft and its code (or a question if details are
missing). A draft is never applied until you reply `yes <code>`; drafts that wait too long expire and nothing changes.

Checking the selection (change requests, not commands; each still needs `yes <code>`):

- `store.confirm_selection`: tell Hass you checked the shelves, for example "I checked the selection today: the
  avocados are in, the eggs are limited, the sourdough is sold out." The site then says "Selection last checked by
  Michael on <day>." and the named products show "Available today", "Limited" or "Sold out". You may name an
  earlier day you checked, never a future one or a day before the last recorded check. Products you do not name keep
  their last word, shown as "Last confirmed <day>" with the day they were last named.
- `product.set_availability`: change one product's word ("the eggs are sold out") after today's check; with no
  check today it is refused with "check the selection first".
- `product.clear_availability`: take one product's word off its card ("stop showing the eggs as sold out"). Only that
  product changes: its word and its own check day are removed, so it is back to not confirmed (no word on the card).
  It never sets "Sold out" and leaves the store's selection check and every other product alone. It needs `yes <code>`
  even if shelf-check changes are set to apply automatically. It is refused when the product has no word set, is
  hidden or is held. `undo` puts the word and its day back exactly as they were.
- Until the first check the site shows no check line and no availability words. If
  the last check is more than a week old when the site is generated, the line adds "(more than a week ago - call or
  visit to confirm)" and the product words become "Last confirmed <day>". Hidden and held products never show them.

A maker without a website: `maker.add` needs only the key, name, place and story; leave `url` out and the maker's
card shows its story and place with no "Visit" link. `maker.edit` with `clearUrl: true` removes a maker's website (it
cannot be combined with `url`); a maker with no website and nothing else changed is refused. Both are change requests that
need `yes <code>`, and `undo` restores the website exactly as it was. A website recorded as a migrated source link
cannot be removed: the change is blocked.

Home-page photo (a change request, needs `yes <code>`): `store.clear_home_image`, for example "put the old photo back",
shows the shop's own photo on the home page again, whatever store changes came after you set yours. It is refused when
no photo of yours is set; `undo` puts your photo back.

Stop carrying a maker (a change request, needs `yes <code>`): `maker.hide` with `withProducts: true`, for example "we stopped
carrying Etto", hides the maker and all of its active products in one change. The proposal lists the maker and every
product id it will hide. Hidden and held products are left exactly as they are. Without `withProducts`, a maker that
still has active products is refused and the reply names them. `undo` brings the maker and every product back together.
