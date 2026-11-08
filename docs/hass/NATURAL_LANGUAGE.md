# What you can say to Hass

Text Hass the way you would text a helper in the shop: short, casual, typos and all. You can type it or dictate it. Hass
reads for what you mean, then shows you a draft. Nothing reaches the website until you reply `yes` with the draft's code,
and every change can be undone. Codes such as `a1b2` are placeholders: use the code in Hass's own reply.

This page is the plain list of what works. The exact commands (`yes`, `no`, `status`, `undo`, `help`) are in the
[phone guide](PHONE_GUIDE.md) and [commands list](COMMANDS.md); what Hass cannot do yet is in [limits](LIMITS.md).

## The one rule: when Hass is not sure, it asks

Hass does not guess. If it cannot tell which product, which day or what time you mean, it sends you **one short
question** that says what it understood and lists the choices, and it changes nothing until you answer.

- You: `honey is sold out`
- Hass: `Which honey should I mark Sold out: Stepladder avocado blossom honey or Big Sur Honey Company honey?`
- You: `the big sur one`  (a short answer is fine: Hass remembers its own question)

Hass remembers its question for 30 minutes <!-- conversation.RECENT_MINUTES -->. After that, or if you have sent something else
in between, it does not connect your answer to the old question, so say the whole thing again.

If you ask for something that is already true, Hass tells you instead of making a change that changes nothing.

- You: `can you change the shop hours to 9 to 5 on saturdays`
- Hass (when Saturday already says 9am to 5pm): `It already says that: Saturday 9am–5pm. Did you mean something else?`

## Things you can say

**Is it in stock?** Plain words are fine.

- `eggs are out`, `egs r sold out again lol`, `no more strawberries today`
- `avocados limited today`, `peppers running low`
- `lemons are back`, `got more honey in`
- A whole shelf: `bread is gone`. Hass drafts one change for each product on a small shelf and asks you first when the
  shelf is big.
- After you check the shelves: `checked the shelves: avocados in, eggs limited, bread sold out`

**Hide or bring back a product or a maker.** `hide the plums`, `take the cashews off the site`, `bring back the lemons`.

**Hikes.** Say what and when; Hass works out the date from today in California time.

- `post a hike at Cass Hill on Saturday at 9, meet at the trailhead gate`
- `cancel the Point Buchon walk, it's raining`
- `move Saturday's hike to 8:30`, `do the Cass Hill hike again on the 29th at 9`
- After a hike: `recap: 12 people, great morning`

If the day could mean two things (`next Saturday` on a Monday can be this week's or the following week's), Hass asks which.

**The shop.** `we're open till 7 on fridays now`, `winter hours: 10 to 4 every day`, `we're closed Thanksgiving`.
Hass sends the whole list of hours back, with the days you did not change repeated as they are.

**Words on the site.** Product descriptions, the home-page notice, maker stories. Hass only writes what you wrote;
it never adds "organic", "local" or where something comes from unless you say it.

**Fix a draft that is waiting.** `actually make that 10am`, `wednesday instead`, `not strawberries, the raspberries`.
With two drafts waiting, Hass changes the one your words are about. If it cannot tell, it asks. A different product or
hike is a new request, not a fix.

**Several things at once.** `eggs out, bread limited, and hide the plums` becomes three changes in one draft.

## Things that are not changes

Hass answers these without drafting anything:

| You say | Hass does |
|---|---|
| `did it go up?`, `is it live`, `what's waiting` | Tells you to send `status` |
| `undo that`, `take it back` | Tells you to send `undo` |
| `never mind`, `scratch that` (with a draft waiting) | Tells you to send `no a1b2` |
| `ok`, `go ahead`, `looks good` | Tells you to send `yes a1b2`. These words never approve anything by themselves |
| `what time do we close saturday?`, `when's the next hike?` | Answers from what the site already says |
| jokes, thanks, off-topic | A short friendly note; nothing changes |

## Things Hass will not do by message

- **Prices.** The website shows no prices. A message that is only a price gets a short reply saying so. If a text change
  also has a price in it, Hass asks you to send it again without the price.
- **Layout, colours, fonts, new pages.** These are design changes and are not available by message yet.
- **Claims.** Organic, origin, health claims and awards cannot be added or removed by chat.
- **Anything you did not say.** `same as last time` or `make it better` gets a question, not a guess.

## If Hass keeps asking the same question

Say it with the full product name once (`Big Sur Honey Company honey is sold out`). If that still does not work,
send `help`, or tell G. Never type a password or anything private into the chat.
