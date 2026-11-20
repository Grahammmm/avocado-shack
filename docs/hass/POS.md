# Hass till views (HASS-POS-1)

What Mike and G can read about the till, in plain English, from the **private cache only**. Local code writes every line from fixed
templates: no model writes or sees till data, nothing is sent anywhere, no token is loaded, no network call is made. This card builds
the engine (`hass/clover/pos.py`) and the private report; the chat commands that call it are a later card. See `CLOVER.md` for the cache,
the read token and the write journal.

## The views

| View | Example (fixture) |
|---|---|
| till summary | `Till at 12:00 pm: 6 items, 2 sold out, 0 running low, 1 with no count. Website: 2 linked, stock words waiting: not available yet. Sold today (includes stock edits): 3 items, 38 units.` |
| price of / how many | `Eggs, dozen: $7.00 each, 0 in the till (as of 12:00 pm).` |
| low stock | the existing stock report: names plus counts, sold out first |
| what sold today / this week | `Sold today (includes stock edits): Eggs, dozen 14, Sunshine olive oil 14, Hass avocado 10 (count drops between till reads, not exact sales)` |
| website vs till | the existing mismatch report as text: each heading with up to five rows |

"Stock words waiting" is not available yet (`stockWordsWaiting` is null in `pos-totals.json`): a stock word that disagrees with the till is not a
pending change, and the real pending/deferred count arrives with the STOCK-SITE totals integration. "Linked" is the saved links less the broken ones.
Links are made with `link suggest` and the owner's `link` commands (docs/hass/CLOVER.md section 2, "The link").

## What sold: count drops, and it includes stock edits

The cache keeps the counts of every read for **14 days** (`snapshots`, written and pruned in the same transaction as the sync, and emptied by a sync to a different configured till; items
the till does not count have no row). The rule is deliberately simple:

- **Sold** for an item is the sum of its **count drops** between consecutive reads in the period. A count that went up is a restock and is ignored, never taken off;
- the period starts at the earliest read from one hour before Pacific midnight of the first day (today, or the last 7 days) and ends at the read now;
- **it includes stock edits.** Hass does not add anything back: a count Hass itself changed (`set_stock`), a recount or a hand edit at the register between two reads
  also shows as a drop. That is why every sold number is labelled "includes stock edits" (chat reply, summary line, report headings and `countDropNote` in `pos-totals.json`);
- an item that has a count now but is missing from one of the reads in the period gets **no number**: the reply says "Left out: <names> (a count was missing in one of the reads)"
  rather than guess, and the summary line and `pos-totals.json` (`countDropLeftOut`, `countDropIncomplete`) say "incomplete: N items left out". A read in which no item had a count still counts as a read (it is kept as a marker row), so 10 -> nothing counted -> 5 leaves the item out. An item counted in an earlier read but absent from the latest item list is also left out (named "an item no longer on the till list"), never 0 sold. An item first seen in the latest read has nothing to compare and is simply not listed;
- `report --all` writes the stock and mismatch reports and the POS summary plus `pos-totals.json`;
- exact sales need the Orders permission, which this card does not use.

No earlier read yet: "I don't have an earlier till count to compare with yet, so I can't say what sold today (includes stock edits) ...".

## Old or missing data

The rules of `reads.py` apply to every view. Up to 20 minutes old: quoted as is. Older: "(till count as of <time>)". When the last sync
failed: "I can't reach the till right now. The last count I have is from <time>, so treat it as old." Over 24 hours old: no count is quoted at all.

## The private report

`python3 hass/clover/cli.py report pos --host host.json [--out DIR]` reads the cache and the local products and links (no
token, no network) and writes into `<state>/clover/reports/` (folder 0700, files 0600, atomic replace, refuses a link or a wider mode):

- `YYYY-MM-DD-pos.md` (Pacific date): the summary, sold today and this week (both labelled "includes stock edits"), low stock and website versus till. Names and prices
  may appear here; it is private and never in git or on the site;
- `pos-totals.json`: **totals only** (counts, `asOf`, `tillReachable`, snapshot state), no item name, price or SKU. Another tool may copy these numbers.

Dated `-pos.md` files of 90 days or more are deleted on each run, like the stock and mismatch reports. Stdout stays one redacted JSON line.
