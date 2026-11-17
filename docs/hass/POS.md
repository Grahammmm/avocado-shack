# Hass till views (HASS-POS-1)

What Mike and G can read about the till, in plain English, from the **private cache only**. Local code writes every line from fixed
templates: no model writes or sees till data, nothing is sent anywhere, no token is loaded, no network call is made. This card builds
the engine (`hass/clover/pos.py`) and the private report; the chat commands that call it are a later card. See `CLOVER.md` for the cache,
the read token and the write journal.

## The views

| View | Example (fixture) |
|---|---|
| till summary | `Till at 12:00 pm: 6 items, 2 sold out, 0 running low, 1 with no count. Website: 2 linked, stock words waiting: not available yet. Count drops today: 3 items, 33 units.` |
| price of / how many | `Eggs, dozen: $7.00 each, 0 in the till (as of 12:00 pm).` |
| low stock | the existing stock report: names plus counts, sold out first |
| what sold today / this week | `Biggest count drops today: Eggs, dozen 14, Sunshine olive oil 14, Hass avocado 5 (count drops, not exact sales: a recount or a till edit also shows here)` |
| website vs till | the existing mismatch report as text: each heading with up to five rows |

"Stock words waiting" is not available yet (`stockWordsWaiting` is null in `pos-totals.json`): a stock word that disagrees with the till is not a
pending change, and the real pending/deferred count arrives with the STOCK-SITE totals integration. "Linked" is the saved links less the broken ones.

## Count drops, not exact sales

The cache keeps the counts of every read for **14 days** (`snapshots`, written and pruned in the same transaction as the sync, and emptied by a sync to a different configured till; items
the till does not count have no row). A drop is the count at the start of the period, less the count now, **plus Hass's own change**:

- the start is the earliest read from one hour before Pacific midnight of the first day (today, or the last 7 days);
- Hass's own changes are the `set_stock` rows of its write journal (`journal.sqlite3`, opened read-only, same till only). Each carries two stamps Hass wrote
  itself: when it recorded its intent to write, and when the change was settled (applied, failed or checked afterwards). Before the stamps there is no
  apply time to rely on. A change settled at or before the start read is already in the start count, and one begun at or after the read now is not in it yet:
  neither is added back. A change begun after the start read and settled before the read now, with a known amount, is added back. Every other change is
  **ambiguous**: one with no stamps, one not settled, one whose amount is unknown (not applied, or no known before/after), or one whose stamps touch a read.
  That item gets no number, and the reply says "Left out: <names> (a Hass till change landed close to a count)" rather than guess. A count Hass lowered is taken off the drop; stock it received is added back, so a delivery does not hide sales;
- a count changed by hand at the register, a recount or a till edit is **not** known, so it also shows as a drop. That is why every reply says
  "count drops, not exact sales". Exact sales need the Orders permission, which this card does not use.

No earlier read yet: "I don't have an earlier till count to compare with yet, so no count drops today (count drops, not exact sales ...)".

## Old or missing data

The rules of `reads.py` apply to every view. Up to 20 minutes old: quoted as is. Older: "(till count as of <time>)". When the last sync
failed: "I can't reach the till right now. The last count I have is from <time>, so treat it as old." Over 24 hours old: no count is quoted at all.

## The private report

`python3 hass/clover/cli.py report pos --host host.json [--out DIR]` reads the cache, the journal and the local products and links (no
token, no network) and writes into `<state>/clover/reports/` (folder 0700, files 0600, atomic replace, refuses a link or a wider mode):

- `YYYY-MM-DD-pos.md` (Pacific date): the summary, count drops today and this week, low stock and website versus till. Names and prices
  may appear here; it is private and never in git or on the site;
- `pos-totals.json`: **totals only** (counts, `asOf`, `tillReachable`, snapshot state), no item name, price or SKU. Another tool may copy these numbers.

Dated `-pos.md` files of 90 days or more are deleted on each run, like the stock and mismatch reports. Stdout stays one redacted JSON line.
