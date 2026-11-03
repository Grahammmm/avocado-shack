# Hass commands (owner card)

These are the only messages Hass treats as commands. Send each one as the whole message. Capital letters in the command
do not matter (`YES A1B2` is the same as `yes a1b2`). Codes are the short codes Hass puts in its replies; `A1B2` below
is only a placeholder.

A trailing `.` or `!` is ignored for every command except `remember` and `forget` (`Status.` and `Memory.` work).
The two note commands are stricter:

- `remember <key>: <text>` saves the text exactly as sent, so its capitals and any final `.` or `!` are kept.
- `forget <key>` ignores a trailing `!` but not a `.`, because a key may contain `.`: `forget parking.` looks for a
  note called `parking.` and leaves the `parking` note alone. Send `forget parking` with no full stop.

| Send | What happens | Example |
| --- | --- | --- |
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. The reply says the change is saved but not on the website yet, because copying it to the website is a separate step. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft or question; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`) | Cancels the waiting draft or question; nothing changes. | `no` |
| `history` | Lists the last five approved changes (approved (still being saved), applied, checked, failed or undone) with their codes and states, each with where it is now (on the website, not confirmed on the website, undone). | `history` |
| `undo` | Drafts an undo of the most recent applied change; a bare undo skips undos and takes the change before. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `status` | Says whether changes are paused, lists waiting drafts and the last result, and upcoming hike seat totals. With a daily limit set, it also shows `Interpreter today: N of CAP` (change requests read today). It also counts `Photos waiting for details: N` and, when any, `Photos still downloading: M` (`unavailable` if the inbox cannot be read). It changes nothing. | `Status.` |
| `did it work?` (or `did that work?`, `did my change work?`): the same as `status` | Answers "did my change work?" in its `Last change:` line: done and on the website now (with the time it was checked), saved but not confirmed on the website (and why; if copying it stopped part way some pages may already show it, so ask for help to copy it again), did not reach the website (the website is unchanged), or undone. It changes nothing. | `did it work?` |
| `stop changes` (or `stop`, `pause`, `pause changes`) | Stops any approval from applying and replies how many requests are waiting. Drafts can still be prepared; changes already on the website stay there. | `stop changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note. | `forget parking` |
| `memory` | Lists the saved notes (up to 20). | `memory` |
| `alias <name>: <id>` | Saves your own name for a product id or maker key that exists now, so a lookup of that name finds it. Send `forget alias.<name with - for spaces>` to remove it. | `alias green jam: photo-product-001` |
| `find <words>` | Lists up to 10 matching products, makers, hikes and route ideas, with ids: products and makers whose name matches (your aliases too), then hikes (by start, with the Pacific weekday, date and time) and route ideas whose title contains every word, each with its status, hidden, cancelled and completed ones included. It changes nothing and works while paused. | `find lion's mane` |
| `show <code>` | Sends that draft again: a waiting draft's full proposal text and its preview screenshot, or an applied change's lines (with its commit) and its checked screenshot. An expired, cancelled or replaced draft is named as such. It changes nothing, expires nothing and works while paused. | `show A1B2` |
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
  earlier day you checked, never a future one or a day before the last recorded check.
- `product.set_availability`: change one product's word ("the eggs are sold out") without a new check date.
- Until the first check the site says "The selection has not been checked yet." and shows no availability words. If
  the last check is more than a week old when the site is generated, the line adds "(more than a week ago - call or
  visit to confirm)" and the product words become "Last confirmed <day>". Hidden and held products never show them.
