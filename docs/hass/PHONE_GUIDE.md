# Hass on your phone: a short guide

Text Hass from Messages like you would text a helper. Nothing reaches the website until you say yes, and every change can be undone. Codes such as `a1b2` below are placeholders: use the short code Hass puts in its own reply. Each message stands on its own. A command (such as `status`) must be the whole message; anything else is read as a change in plain words.

## Add a product
1. Describe the product in plain words: its name, what it is, and who makes it. A photo of it with those words works too.
   Send (plain words): `Add a new product called Hass avocado jam made by our own kitchen`
2. Hass replies with one draft (the item, a new maker's story, the tidied picture) and its code, or asks one question at a time, for a new maker: "What should we say about Harbor Lane? A sentence is enough." Answer in plain words, or say skip. Hass never makes up a story.
3. Read the draft. When it looks right, approve it with its code.
   Send: `yes a1b2`
4. To take a stock word such as sold out off a product, ask in plain words. This does not mark it available.
   Send (plain words): `stop showing the eggs as sold out`
5. A new maker and its first product are one request. Hass asks for any missing fact or the photo; nothing applies before you approve. A website is optional: say there is none, Hass never makes one up.
   Send (plain words): `Add a new maker called Example Orchard and its first product, pear jam`
   Send (plain words): `Add a maker called Example Orchard; it has no website`
6. To stop carrying a maker, Hass drafts hiding the maker and its active products together. Held products stay as they are, a refusal changes nothing, undo brings back just that change.
   Send (plain words): `Stop stocking Example Orchard and hide its products`

Tip: Hass replies again when the change is saved and whether it is on the website. Hass never invents organic claims or farm origins. A photo on a busy shelf gets a request to retake it on a plain surface. One undo removes the whole item. See NEW-ITEM-FLOW.md.

## Add a photo
1. Send one to four photos in one message, as JPEG or PNG, the right way up. Each photo gets its own draft code, in the order sent, and Hass asks which product it is for and for a few words describing it. If any photo is not usable, none is saved. A caption on several photos is ignored.
2. Answer in plain words: the product, or the home page; your words become the picture's alt text. With several photos, repeat the answer for each actual code.
   Send (plain words): `It is for the Hass avocado, a crate of ripe avocados on the counter`
   Send (plain words): `Use this for the home page, a crate of ripe avocados on the counter`
   Send (plain words): `For draft a1b2, use this on the home page: avocados in a wooden crate`

Tip: Approve each photo's draft separately with its own code, as in `yes a1b2`. Your answer is not an approval and a caption is never a command: send any `yes` as its own message. Hass has no text command that sends photos.

## Post a hike
1. Describe the hike in plain words: the trail, the date and start time, and where to meet.
   Send (plain words): `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate`
2. Hass replies with a draft and its code, or asks for a missing detail such as the meeting point (it never makes up trail facts). Approve the draft with its code (`yes` plus the code, as in Add a product).
3. Check upcoming hikes and their seat totals at any time.
   Send: `status`
4. Hide or bring the sample hikes back. Each is a draft you approve with its code, and undo puts it back.
   Send (plain words): `hide the sample hikes`
   Send (plain words): `bring the sample hikes back`
5. Repeat a hike on a new date (use an existing hike's exact id, walk-001 is only an example). Hass asks for missing details and copies no guests, RSVPs or recap.
   Send (plain words): `Repeat hike walk-001 on 2026-12-06 at 09:00`
6. Cancel a hike with a one-line note (walk-001 is only an example; use the exact id). The note appears on the cancelled card; guests are not messaged.
   Send (plain words): `Cancel hike walk-001 with the note: Rained out - we will pick a new date soon.`
7. Change the hiking club's opening paragraph. This edits the club page copy only, still a draft you approve; it is not an announcement or the store intro.
   Send (plain words): `Set the hiking club opening paragraph to: Walk with us along the coast, share the trail, and leave room for discovery.`

## Change opening hours
1. Write the new hours in plain words, one line per day or group of days. Hass replies with a draft and its code; approve it with its code.
   Send (plain words): `Change the opening hours to Monday to Friday 9am to 6pm and Saturday 9am to 4pm`
2. A home notice can start later: give the first and last day (Pacific, both included, today or later). Before the first day it stays hidden. Without JavaScript it appears at the next regeneration. Hass sends no message to guests.
   Send (plain words): `Set the home notice to "Closed Thanksgiving Day" from 2026-11-26 through 2026-11-26.`

Tip: changed your mind before approving? Cancel the draft and nothing changes.
Send: `no a1b2`

## Change the home page
1. Change the headline (two lines, up to 40 characters each).
   Send (plain words): `Set the home page headline: first line "A little market.", second line "A lot to discover."`
2. Change the story paragraph.
   Send (plain words): `Change the home page story to: We are a small shop in Morro Bay selling fruit, bread and cheese from people we know.`
3. Change the big photo: send one photo on its own, then say it is for the home page and describe it.
   Send (plain words): `Not a product, that one is for the top of the home page. Describe it as: Avocado Shack storefront with a green awning`
4. Show a notice at the top of the home page through its last day.
   Send (plain words): `Put a notice on the home page: "Closed Thanksgiving Day", until 2026-11-26.`
5. Set the store phone number shown on the website.
   Send (plain words): `Our phone number is 805 555 0123`
6. Put the shop's own home photo back. This is a draft too.
   Send (plain words): `put the old photo back`

Tip: approve each draft with its code. A notice's last day is today or up to 60 days ahead (Pacific); a new notice replaces the old one, and undo removes it.

## Route ideas
1. Add an idea with its source name and link; without a source Hass asks for one.
   Send (plain words): `Add a route idea "Montana de Oro bluffs" in Los Osos: cliffs and coves, 4 miles, moderate, 250 ft elevation change, about 2 hours, a loop on dirt trail and open bluffs, described as "A loop along the bluffs with views of the coves." Source: "Park trail guide", https://example.com/mdo-bluffs`
2. Take an idea off the route list, and bring it back.
   Send (plain words): `Take the Cass Hill walk off the route list.`
   Send (plain words): `Put the Cass Hill walk back on the route list.`

Tip: Hass will not hide an idea while a scheduled hike uses it; change that hike first. Approve each draft with its code.

## Undo a change
1. See the last few changes with their codes, or search for older ones: send history and some words; every word must be in the summary, newest matches first with code and current state.
   Send: `history`
   Send: `history notice`
2. Ask for an undo of the change you want to take back, using its code. Hass replies with an undo draft and a new code.
   Send: `undo a1b2`
3. Approve it with that new code.
   Send: `yes a1b2`

Tip: an undo is a draft like any other, so nothing goes back until you say yes with its new code. An older shop-detail change (such as a notice) can be undone while keeping a later shelf check or other detail; a later edit of the same detail is a conflict and the undo is refused. Not every older change can be undone.

## Pause and resume
1. Stop all approvals from applying, for example while you are away.
   Send: `pause changes`
2. Check that changes are paused and see which drafts are waiting.
   Send: `status`
3. Read one saved listing, using an id from `find`. It changes nothing, works while paused and is not a live check of the website.
   Send: `listing photo-product-001`
4. When you are ready again, let approvals apply.
   Send: `resume changes`
5. Approve any waiting draft you still want with its code (`yes a1b2` as before). A written proposal that expired within the last seven days can be renewed if the site still matches. Hass gives a new code and expiry; approve it separately with `yes` and the new code. A photo, a question, a cancelled, replaced or applied draft is not renewed.
   Send: `again a1b2`

Tip: resuming never applies a waiting draft by itself, and drafts that wait too long expire with nothing changed.

More commands, each as its own message: `report` replies your morning shelf report, `post Hass avocado` a draft photo caption, and `post hike` plus a hike's name a hike announcement draft, `post maker` plus a maker's name a caption text only. None of them posts or changes anything. Forgot a command? Send `help`. Prices (private): save what you paid, then ask for a suggested price. The cost is private; it is never on the website.
Send: `post hike Point Buchon`
Send: `post maker Example Orchard`
Send: `cost Hass avocado: 24 for 12`
Send: `margin Hass avocado at 35%`
For what Hass cannot do yet see [Known limits](LIMITS.md), and for every command see [the command card](COMMANDS.md).
