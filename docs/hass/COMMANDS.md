# Hass commands (owner card)

These are the only messages Hass treats as commands. Send each one as the whole message. Capital letters do not matter
(`YES A1B2` is the same as `yes a1b2`), and a trailing `.` or `!` is ignored (`Status.` works). Codes are the short
codes Hass puts in its replies; `A1B2` below is only a placeholder.

| Send | What happens | Example |
| --- | --- | --- |
| `yes <code>` (or `approve <code>`, `approved <code>`) | Applies that draft, then replies when it is done and checked. | `YES A1B2` |
| `yes` alone (or `approve`, `approved`) | Applies the one waiting draft. If more than one is waiting, Hass asks which. | `approve` |
| `no <code>` (or `cancel <code>`, `reject <code>`) | Cancels that draft; nothing changes on the site. | `cancel A1B2` |
| `no` alone (or `cancel`, `reject`) | Cancels the one waiting draft; nothing changes. | `no` |
| `history` | Lists the last five changes with their codes and states. | `history` |
| `undo` | Drafts an undo of the most recent applied change. It needs `yes <code>` like any draft. | `undo` |
| `undo <code>` | Drafts an undo of that applied change. It needs `yes <code>`. | `undo A1B2!` |
| `status` | Says whether changes are paused, lists waiting drafts and the last result, and upcoming hike seat totals. It changes nothing. | `Status.` |
| `pause` or `pause changes` | Stops any approval from applying. Drafts can still be prepared. | `pause changes` |
| `resume` or `resume changes` | Lets approvals apply again. It never applies a waiting draft by itself. | `resume changes` |
| `remember <key>: <text>` | Saves a note for Hass (key: a-z, 0-9, `.` or `-`). Sending the same key again updates it. | `remember parking: use the back lot` |
| `forget <key>` | Deletes that saved note. | `forget parking` |
| `memory` | Lists the saved notes (up to 20). | `memory` |

Saved notes never change the site, and pause does not affect them.

Any other message is read as a change request. Hass replies with a draft and its code (or a question if details are
missing). A draft is never applied until you reply `yes <code>`; drafts that wait too long expire and nothing changes.
