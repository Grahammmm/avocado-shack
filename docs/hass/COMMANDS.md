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
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft or question; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`) | Cancels the waiting draft or question; nothing changes. | `no` |
| `history` | Lists the last five changes with their codes and states. | `history` |
| `undo` | Drafts an undo of the most recent applied change. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `status` | Says whether changes are paused, lists waiting drafts and the last result, and upcoming hike seat totals. With a daily limit set, it also shows `Interpreter today: N of CAP` (change requests read today). It also counts `Photos waiting for details: N` and, when any, `Photos still downloading: M` (`unavailable` if the inbox cannot be read). It changes nothing. | `Status.` |
| `pause` or `pause changes` | Stops any approval from applying. Drafts can still be prepared. | `pause changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note. | `forget parking` |
| `memory` | Lists the saved notes (up to 20). | `memory` |
| `alias <name>: <id>` | Saves your own name for a product id or maker key that exists now, so a lookup of that name finds it. Send `forget alias.<name with - for spaces>` to remove it. | `alias green jam: photo-product-001` |
| `find <words>` | Lists up to 10 products and makers whose name matches (your aliases too), each with its id and status, hidden ones included. It changes nothing and works while paused. | `find lion's mane` |
| `help` (or `commands`, `?`) | Replies a short list of every command with one example each. It changes nothing. | `help` |

Saved notes never change the site, and pause does not affect them.

Photos: send one photo per message, as JPEG or PNG, up to 20 MB, the right way up (a photo that only shows upright
because of a camera rotation tag is refused). Any other file, or a photo that is too large, incomplete or unreadable,
gets a reply naming the limit, and nothing is saved or drafted.

Any other message is read as a change request. Hass replies with a draft and its code (or a question if details are
missing). A draft is never applied until you reply `yes <code>`; drafts that wait too long expire and nothing changes.
