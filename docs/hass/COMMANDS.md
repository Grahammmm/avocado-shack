# Hass commands (owner card)

In live mode, proposals show the full previous text and name the site the change goes live on.
Approval must name the draft: `yes a1b2`, not a bare `yes`. A bare `no` still cancels.
A protected change says it cannot go live from chat. A saved reply is not a website outcome;
Hass sends a separate message about the website.

These are the only messages Hass treats as commands. Send each one as the whole message. Capital letters in the command
do not matter (`YES A1B2` is the same as `yes a1b2`). Codes are the short codes Hass puts in its replies; `A1B2` below
is only a placeholder.

A trailing `.` or `!` is ignored for every command except `remember` and `forget` (`Status.` and `Memory.` work). A trailing `?` is also ignored, but only for the read-only commands `status`, `history`, `report`, `memory`, `find`, `show`, `post`, `listing`, `hidden`, `margin` and `help` (`status?`, `find eggs?` and `show a1b2?` work). A `?` never runs `yes`, `no`, `undo`, `stop`, `resume`, `remember`, `forget` or `alias`.
The two note commands are stricter:

- `remember <key>: <text>` saves the text exactly as sent, so its capitals and any final `.` or `!` are kept.
- `forget <key>` ignores a trailing `!` but not a `.`, because a key may contain `.`: `forget parking.` looks for a
  note called `parking.` and leaves the `parking` note alone. Send `forget parking` with no full stop.
- A note name may have spaces, as an alias name does: they become `-` and capitals fold, so `remember Parking Spot: use the back lot`
  saves `parking-spot` (the reply names that key) and `forget parking spot` removes it. A name still invalid after that gets
  the usual refusal. `forget it` removes a note called `it`; `forget it all` is not a command.

A yes or no with its code works in either order and survives everyday phone typing: commas and other punctuation, emoji and the words please, thanks, thank you, ok and okay are ignored, so `Yes, a1b2`, `yes a1b2 thanks`, `A1B2 yes` and `no a1b2 please` act as `yes a1b2` and `no a1b2`. Any other word keeps its meaning: `yes but make it 10am` and `no, 5pm` are still change requests.

A question mark means a question, never an answer. `yes a1b2?`, `no a1b2?`, `a1b2 yes?`, `yes?`, `no?`, a waiting code on its own (`a1b2` or `a1b2?`) and similar forms apply nothing, cancel nothing, record no approval and make no interpreter call. Hass replies `Nothing was changed. To apply a1b2, reply yes a1b2; to cancel it, no a1b2.` (with no or an unknown code, it lists the waiting codes).

| Send | What happens | Example |
| --- | --- | --- |
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. The reply says the change is saved but not on the website yet, because copying it to the website is a separate step. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft or question; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`) | Cancels the waiting draft or question; nothing changes. | `no` |
| `history` | Lists the last five approved changes in plain words, each with where it is now (on the website, saved but not confirmed on the website, or undone). It reads the audit log (docs/hass/AUDIT.md), so a change on the till is listed too ("A change on the test till: saved."). With none yet it says "We haven't made any changes yet." It changes nothing. | `history` |
| `history <words>` | Lists up to 10 approved changes, newest first, whose summary contains every word you send, each with where it is now; capital letters and accents do not matter, and the words may come in any order. Only the summary is searched, across all approved history. Send 1–60 characters; no match says so ("I found no changes that match ..."), and no words gets a usage reply. It changes nothing, expires nothing and works while paused. | `history opening hours` |
| `undo` | Drafts an undo of the most recent applied change; a bare undo skips undos and takes the change before. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `status` | Says in plain words whether changes are paused (or that Hass is having trouble reading your messages), what is waiting for your yes or for details, when you last did the shelf check (or that it is still needed), upcoming hike seat totals and your last change. Near the daily limit it adds "I'm close to the number of new requests I can read today." It also mentions photos that are waiting for details or still downloading when there are any. It changes nothing. | `Status.` |
| `did it work?` (or `did that work?`, `did my change work?`): the same as `status` | Answers "did my change work?" in its `Last change:` line: done and on the website now (with the time it was checked), saved but not confirmed on the website (and why; if copying it stopped part way some pages may already show it, so ask for help to copy it again), did not reach the website (the website is unchanged), or undone. It changes nothing. | `did it work?` |
| `stop changes` (or `stop`, `pause`, `pause changes`) | Stops any approval from applying and replies how many requests are waiting. Drafts can still be prepared; changes already on the website stay there. | `stop changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`; spaces in the key become `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note (spaces in the key become `-`). | `forget parking spot` |
| `memory` | Lists your saved notes (up to 20, under "Notes I'm keeping:"), then your nicknames apart (up to 20, then "And a few more."); notes and nicknames are counted and capped separately. A nickname line shows the product or maker name as it is on the website now, and says when it is hidden or on hold. A nickname whose product or maker is gone says so and how to forget it; when the saved copy cannot be read right now it says that, and nothing is deleted. It only reads: it changes nothing, does not expire drafts, and works while paused. | `memory` |
| `alias <name>: <product or maker>` | Saves your own nickname for a product or maker that exists now (say its name), so a lookup of that nickname finds it, and a plain-word change request ("the green jam is sold out") can use it to pick that record. Only nicknames whose record still exists, the newest 50, reach change requests; a nickname never establishes a claim. Send `forget alias <name>` to remove it. If a note named `alias-<name>` is saved and no nickname has that name, `forget alias <name>` removes the note; if both exist nothing is forgotten and the reply names the two exact forgets. | `alias green jam: Linn's blueberry preserves` |
| `cost <product>: <pack cost> for <units>` | Saves what you paid for one purchase of a product (say its name; it must exist now, any status), as your private note; sending a new cost updates it and says what it was. A number that is out of range is named in plain words. The cost is never on the website, in a draft or in what is sent to the interpreter; `memory` shows it to you and `forget cost.<product id>` removes it. `remember cost...` does not work, use this command. It changes no price and works while paused. | `cost Hass avocado: 24 for 12` |
| `find <words>` | Lists up to 10 matching products, makers, hikes and route ideas by name (your nicknames too), each with its status in plain words (hidden, cancelled and done ones included) and hikes with the weekday, date and time. More than 10 ends with "There are more. Add a word to narrow it down." It changes nothing and works while paused. | `find lion's mane` |
| `show <code>` | Sends that draft again: a waiting draft's full proposal text and its preview screenshot, or an applied change's lines (with its commit) and its checked screenshot. An expired, cancelled or replaced draft is named as such. It changes nothing, expires nothing and works while paused. | `show A1B2` |
| `report` (or `morning report`) | Replies the morning shelf report from your last shelf check (Pacific today): when you last checked, counts of available, limited, sold out and not confirmed products, the limited and sold-out names, and hikes today or tomorrow. These are shelf checks, not stock counts. It then adds a `Waiting for you:` block: each draft waiting for your yes or for details (code and summary, the same lines as `status`) and `Photos waiting for details: N`, or `Waiting for you: nothing`. It changes nothing on the site, expires nothing and works while paused. When today's shelf check is missing it ends with "Is the shelf list right for today? Reply yes if it is, or tell me what is different.", the first time that day; your bare `yes` then drafts the check for your normal approval. | `report` |
| `post <product>` | Replies a draft Instagram-style caption for that active product (its name, description and maker) with its site photo attached, then what the photo shows. Say the product's name; several words count as this command only when they name a product, otherwise the message is read as an ordinary request. Nothing is posted, scheduled or saved. A product that is unknown, not on the website or without a photo gets a plain-words reply. It changes nothing and works while paused. | `post Hass avocado` |
| `post hike <hike>` | Replies a ready-to-copy announcement draft for that scheduled, upcoming hike (title, time, meeting point, route). Say the hike's name. Nothing is posted, scheduled or saved. A hike that is unknown, cancelled, already past or not scheduled gets a plain-words reply. It changes nothing and works while paused. | `post hike Point Buchon` |
| `margin <pack cost> for <units> at <margin>%` (optional `shrink <S>%`) | Replies one friendly answer: the price to charge, what each one costs you, what you would earn and roughly what percentage that is, and that it is only an idea (nothing on the website changes). A `$` before the pack cost and spaces around the numbers are fine; without `shrink` it is 0%. A number that is out of range is named in plain words; a message that starts with `margin` but is not in this form gets the one-line form to send. It stores nothing, puts no price on the site, does not read a change request and works while paused. | `margin 24.00 for 12 at 35%` |
| `margin <product> at <margin>%` (optional `shrink <S>%`) | Uses the cost you saved with `cost` for that product (say its name): replies "Using the cost you gave me <when>." and then the same answer as the form above. With no saved cost it says it has none and how to save one; a margin out of range is named. It stores nothing, drafts no price change and works while paused. | `margin Hass avocado at 35%` |
| `hidden` | Lists the hidden products, then the hidden makers (marked as makers), by name, up to 20, then "And a few more.", and says how to bring one back ("Bring back <name>"). Held products are never listed. With nothing hidden it says so. It changes nothing and works while paused. | `hidden` |
| `listing <name>` | Replies what the saved copy shows for one product, maker, hike or route idea, starting "This is from my saved copy, not a live look at the website:" with its name, status, place and so on in plain words; anything not saved reads "nothing yet". Say a name or part of one; several words count as this command only when they name something. If more than one thing fits it asks you to say a bit more of its name. It changes nothing and works while paused. | `listing Etto` |
| `photos to take` | Lists the first five active products that still show a stock picture instead of your own photo, with their shelves, then says to ask again for the next few and to send a photo with the product's name as its caption. Hidden and held products are left out. It reads the saved copy (not a live look at the website) and goes by the picture's file name only: it does not look at the picture or prove where one came from. It changes nothing, does not expire drafts, and works while paused. | `photos to take` |
| `help` (or `commands`, `?`) | Replies the fixed command examples, then every registered skill grouped by pack with its approval, private-test support and status. This is the code's list, not proof of what is installed or live. The same list is in [What Hass can do](CAPABILITIES.md). It changes nothing. | `help` |
| `backlog` | Lists the last 10 things you asked that Hass could not do yet (the request number, the day and one line), newest first, or says nothing is written down. It shows no more than that one line of what you sent, changes nothing on the website, and works while paused. | `backlog` |
| `forget backlog.<n>` | Takes that one request off the `backlog` list (the number is never used again). Only one at a time; there is no way to clear the whole list. This is the only `forget` that does not touch a saved note, so `backlog.<n>` cannot be a note name. | `forget backlog.3` |

Saved notes never change the site, and pause does not affect them.

Cancelling a hike (a change request, needs `yes <code>`; not the `cancel <code>` command above, which only rejects a
waiting draft): say it in your own words, for example "cancel the Point Buchon hike, rained out - we will pick a new
date soon". `hike.cancel` takes the hike id and an optional `note`, for example `Rained out - we will pick a new date soon`.
The note is one line of plain text, at most 160 characters, and is public site copy: the cancelled hike's card shows it
exactly as written, above "This hike is cancelled." It is checked like other hike text (no markup, `$` or invisible
characters), and any claim in it, such as a distance or "organic", must come from your own message. Without a note the
card is unchanged. Cancelling notifies nobody. `undo` brings the hike back as scheduled and removes the note.

Photos: send one photo per message, as JPEG or PNG, up to 20 MB. A phone photo's rotation is kept, so it shows upright
(only that rotation tag is kept, never its location, camera or date); only a PNG with a rotation tag is refused. Any
other file, or a photo that is too large, incomplete or unreadable,
gets a reply naming the limit, and nothing is saved or drafted.

A new product needs one brand. The card label (`displayBrand`) is optional: left out, the card shows that brand, and the
exact brand `Producer not identified` shows `From the market`. Give a label only to show something different; it changes
the card label only, not the maker link. Example: `Add Test Orchard quince, brand Test Orchard` with the photo. Hass
still asks for any other missing required fact and never invents one; the draft still needs `yes <code>`, and `undo`
works as for any change.

Two kinds of whole message are not change requests and never reach the interpreter or the daily count: only thanks or
a greeting (`thanks`, `thank you`, `great, thanks`, `hi`, `hello`, `good morning`, any case, with a final `.`, `!` or
`?`), or only emoji. Emoji that are all thumbs-up, OK-hand or check marks get the near-approval answer (nothing is
applied; reply `yes <code>` to approve). Anything else of this kind gets `Nothing changed. Send a change in plain
words, or help.` They work while paused and after the daily limit, and nothing is approved. A message with any other
word, such as `thanks, make the eggs sold out`, is read as below.

Any other message is read as a change request. Hass replies with a draft and its code (or a question if details are
missing). A draft is never applied until you reply `yes <code>`; drafts that wait too long expire and nothing changes.

New products (a change request, needs `yes <code>`): a product you add shows a "New" badge on its card for its first
14 days (counted in Pacific calendar days from the day it was added, worked out in the visitor's browser). Editing,
hiding or restoring a product, or undoing and restoring an add, never starts the 14 days again, and the products that
were already on the site have no "New" badge.

Checking the selection (change requests, not commands; each still needs `yes <code>`):

- `store.confirm_selection`: tell Hass you checked the shelves, for example "I checked the selection today: the
  avocados are in, the eggs are limited, the sourdough is sold out." The site then says "Selection last checked by
  Michael on <day>." and the named products show "Available today", "Limited" or "Sold out". You may name an
  earlier day you checked, never a future one or a day before the last recorded check. Products you do not name keep
  their last word, shown as "Last confirmed <day>" with the day they were last named.
- `product.set_availability`: change one product's word ("the eggs are sold out") after today's check. With no check
  today (none yet, or an older one) Hass does not refuse: it asks "Before I change that, is the shelf list right for
  today? Reply yes if it is, or tell me what is different.", keeps your request, and writes nothing. Your own bare `yes`
  then drafts one change that records today's check and makes the original change, which still waits for your normal
  `yes`; `no` closes the question and changes nothing; any other message is read as your next request (and an
  availability change asks again). The question closes after 30 minutes or at your next message of any kind, only you can
  answer it, and `yes <code>` still only approves that draft. A check dated after today is not asked about: Hass says the
  date looks wrong.
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
