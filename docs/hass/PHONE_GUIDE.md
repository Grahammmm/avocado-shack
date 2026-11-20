# Hass on your phone: a short guide
Text Hass from Messages like you would text a helper. Nothing reaches the website until you say yes, and every change can be undone. Codes such as `a1b2` below are placeholders: use the short code Hass puts in its own reply. Each message stands on its own. A command (such as `status`) must be the whole message, and so is a code-only reply; a change or question goes in plain words. Thanks, hello or an emoji gets a reply that changes nothing, not a draft: `thanks` makes no change, and a thumbs-up is not an approval (when a draft is waiting Hass asks for `yes` and its code). Prices never appear on the website, so nothing is drafted for a price-only change: send it again without the price. A price request is still read like any other message.
Send (plain words): `thanks`
Send (plain words): `👍`
Send (plain words): `Set the quince price to $3`
## Add a product
1. Describe the product in plain words: its name, what it is, and who makes it. A photo of it with those words works too.
   Send (plain words): `Add a new product called Hass avocado jam made by our own kitchen`
2. Hass replies with one draft (the item, a new maker's story, the tidied picture) and its code, or asks one question at a time, for a new maker: "What should we say about Harbor Lane? A sentence is enough." Answer in plain words, or say skip. Hass never makes up a story. Read the draft. When it looks right, approve it with its code. A short reply around the code works too: it approves only the draft that code names, after you have read it. The code alone changes nothing and Hass answers how to approve or cancel, so it is a hint, never an approval. A code Hass does not know, a draft that has expired or a `?` never approves.
   Send: `yes a1b2`
   Send (decorated yes): `Yes, a1b2 thanks`
   Send (code only): `a1b2`
3. To take a stock word such as sold out off a product, ask in plain words. This does not mark it available.
   Send (plain words): `stop showing the eggs as sold out`
4. A new maker and its first product are one request. Hass asks for any missing fact or the photo; nothing applies before you approve. A website is optional: say there is none, Hass never makes one up.
   Send (plain words): `Add a new maker called Example Orchard and its first product, pear jam`
   Send (plain words): `Add a maker called Example Orchard; it has no website`
5. To stop carrying a maker, Hass drafts hiding the maker and its active products together. Held products stay as they are, a refusal changes nothing, undo brings back just that change.
   Send (plain words): `Stop stocking Example Orchard and hide its products`
6. Name a product by an alias you saved earlier (`find` gives the id, `memory` lists your aliases); naming it adds no facts. A new product needs one brand, not a second card brand, and Hass still asks for any other missing fact or the photo. A maker may have no story: Hass never invents one; add it later, with your approval.
   Send (plain words): `Make the green jam sold out`
   Send (plain words): `Add Test Orchard quince, brand Test Orchard`
   Send (plain words): `Add a maker called Test Orchard, with no story`
7. To set a whole shelf or one maker at once, say so in plain words. Hass makes one draft for the changed active products in it: read the count and names, then approve its one code. Hidden and held products stay out, only availability words change (the shelf-check date does not change), and Hass does not promise live stock or approve it for you. Tip: Hass replies again when the change is saved and whether it is on the website. Hass never invents organic claims or farm origins. A photo on a busy shelf gets a request to retake it on a plain surface. One undo removes the whole item. See NEW-ITEM-FLOW.md.
   Send (plain words): `All the vegetables are in today`
   Send (plain words): `Everything from Cal Poly is sold out`
## Add a photo
1. Send one to four photos in one message, as JPEG or PNG, the right way up. Each newly accepted photo gets its own draft code, in the order sent, and Hass asks which product it is for and for a few words describing it. A photo already waiting, repeated in the same message, or already on a product does not get a new draft code; Hass tells you instead. If any photo is not usable, none is saved. A caption on several photos is ignored. Answer in plain words: the product, or the home page; your words become the picture's alt text. With several photos, repeat the answer for each actual code. Approve each photo's draft separately with its own code, as in `yes a1b2`. Your answer is not an approval and a caption is never a command: send any `yes` as its own message. Hass has no text command that sends photos.
   Send (plain words): `It is for the Hass avocado, a crate of ripe avocados on the counter`
   Send (plain words): `Use this for the home page, a crate of ripe avocados on the counter`
   Send (plain words): `For draft a1b2, use this on the home page: avocados in a wooden crate`
2. List the saved active products that still use a catalog picture; this is not a live-site or photo-authenticity check. A replacement still goes through the photo, draft and code steps above.
   Send: `photos to take`
## Post a hike
1. Describe the hike in plain words: the trail, the date and start time, and where to meet.
   Send (plain words): `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate`
2. Hass replies with a draft and its code, or asks for a missing detail such as the meeting point (it never makes up trail facts). Approve the draft with its code (`yes` plus the code, as in Add a product). Check upcoming hikes and their seat totals at any time with `status`.
3. Hide or bring the sample hikes back. Each is a draft you approve with its code, and undo puts it back.
   Send (plain words): `hide the sample hikes`
   Send (plain words): `bring the sample hikes back`
4. Repeat a hike on a new date (use an existing hike's exact id, walk-001 is only an example). Hass asks for missing details and copies no guests, RSVPs or recap.
   Send (plain words): `Repeat hike walk-001 on 2026-12-06 at 09:00`
5. Cancel a hike with a one-line note (walk-001 is only an example; use the exact id). The note appears on the cancelled card; guests are not messaged.
   Send (plain words): `Cancel hike walk-001 with the note: Rained out - we will pick a new date soon.`
6. Change the hiking club's opening paragraph. This edits the club page copy only, still a draft you approve; it is not an announcement or the store intro.
   Send (plain words): `Set the hiking club opening paragraph to: Walk with us along the coast, share the trail, and leave room for discovery.`
## Change opening hours
1. Write the new hours in plain words, one line per day or group of days. Hass replies with a draft and its code; approve it with its code.
   Send (plain words): `Change the opening hours to Monday to Friday 9am to 6pm and Saturday 9am to 4pm`
2. A home notice can start later: give the first and last day (Pacific, both included, today or later). Before the first day it stays hidden. Without JavaScript it appears at the next regeneration. Hass sends no message to guests. Tip: changed your mind before approving? Cancel the draft and nothing changes.
   Send (plain words): `Set the home notice to "Closed Thanksgiving Day" from 2026-11-26 through 2026-11-26.`
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
6. Put the shop's own home photo back. This is a draft too. Tip: approve each draft with its code. A notice's last day is today or up to 60 days ahead (Pacific); a new notice replaces the old one, and undo removes it.
   Send (plain words): `put the old photo back`
## Route ideas
1. Add an idea with its source name and link; without a source Hass asks for one.
   Send (plain words): `Add a route idea "Montana de Oro bluffs" in Los Osos: cliffs and coves, 4 miles, moderate, 250 ft elevation change, about 2 hours, a loop on dirt trail and open bluffs, described as "A loop along the bluffs with views of the coves." Source: "Park trail guide", https://example.com/mdo-bluffs`
2. Take an idea off the route list, and bring it back. Tip: Hass will not hide an idea while a scheduled hike uses it; change that hike first. Approve each draft with its code.
   Send (plain words): `Take the Cass Hill walk off the route list.`
   Send (plain words): `Put the Cass Hill walk back on the route list.`
## Undo a change
1. See the last few changes with their codes, or search for older ones: send history and some words; every word must be in the summary, newest matches first with code and current state.
   Send: `history`
   Send: `history notice`
2. Ask for an undo of the change you want to take back, using its code. Hass replies with an undo draft and a new code; approve it with that new code (`yes` plus it, as above).
   Send: `undo a1b2`
3. `undo that` picks only the last change when that is safe and unambiguous, and makes a new undo draft that needs its own new `yes` code. `never mind` cancels a waiting draft or question without undoing anything; if unclear which, Hass asks instead of guessing. Tip: history times are when a change was approved, in Pacific time, not a website freshness guarantee; old rows may say `time unknown`. An undo is a draft like any other, so nothing goes back until you say yes with its new code. An older shop-detail change (such as a notice) can be undone while keeping a later shelf check or other detail; a later edit of the same detail is a conflict and the undo is refused. Not every older change can be undone.
   Send: `undo that`
   Send: `never mind`
## Pause and resume
1. Stop all approvals from applying, for example while you are away.
   Send: `pause changes`
2. Check that changes are paused and see which drafts are waiting. A closing `?` works on read-only commands such as `status` and `find`; it is never an approval or an undo, so `yes a1b2?` approves nothing and `undo a1b2?` undoes nothing.
   Send: `status`
   Send: `status?`
   Send: `find eggs?`
3. Read one saved listing, using an id from `find`. It changes nothing, works while paused and is not a live check of the website.
   Send: `listing photo-product-001`
4. When you are ready again, let approvals apply.
   Send: `resume changes`
5. Approve any waiting draft you still want with its code (`yes a1b2` as before). A written proposal that expired within the last seven days can be renewed if the site still matches. Hass gives a new code and expiry; approve it separately with `yes` and the new code. A photo, a question, a cancelled, replaced or applied draft is not renewed.
   Send: `again a1b2`
Tip: resuming never applies a waiting draft by itself, and drafts that wait too long expire with nothing changed. More commands, each as its own message: `report` replies your morning shelf report, `post Hass avocado` a draft photo caption, `post hike Point Buchon` a hike announcement draft and `post maker Example Orchard` a caption text only. None of them posts or changes anything. Forgot a command? Send `help`. Prices (private): save what you paid (`cost Hass avocado: 24 for 12`), then ask for a suggested price (`margin Hass avocado at 35%`). The cost is private; it is never on the website. Shortcuts, each its own whole message, read saved data (not a live check of the website) and change nothing: `shelf` reads the saved website words for a shelf, `listing store` the saved shop facts, and `post` or `listing` with a product name or alias needs one unique active match (several matches: Hass asks which). `post` only prepares a caption or photo and never publishes. `no all` cancels every waiting draft and question, keeps stored photos and changes nothing on the website; each approval still needs its own code, and `yes all` is refused. `help undo` explains one command and runs nothing. Two checks are private estimates: they save nothing and put no price on the website. `margin 24 for 12 price 3.49` shows the margin a shelf price gives; `margin 24 for 12 at 35% ending .99` suggests a price rounded up to a .99 ending, never lower than the margin needs (the numbers are made up). If the product still shows an illustration made from a shelf photo, the `post` reply starts with a warning that the picture is not a photo of the product; an owner photo gets no warning. Either way only a draft caption comes back: nothing is uploaded, sent or published.
Send: `post maker Example Orchard`
Send: `shelf vegetables`
Send: `listing store`
Send: `post sourdough`
Send: `listing sourdough`
Send: `no all`
Send: `help undo`
Send: `margin 24 for 12 price 3.49`
Send: `margin 24 for 12 at 35% ending .99`
A mistyped command gets only a guess and nothing runs: `histroy` gets `Did you mean history? Send history.`, so send `history` again as a whole message. When status says Hass could not read a written request (the reader was not working), nothing was drafted: send that change again once it is back; the wording need not change. When it could not read a photo's caption, Hass keeps the photo as a draft waiting for details: once the reader is back, reply with the product and what the photo shows. Sending the same photo again is refused as a duplicate and its caption is not read. If status says the photo's time ran out, send the photo again with its caption. Hass does not retry by itself. A layout idea Hass cannot make by message is kept on the shop computer as a design note for the developer; the website stays as it is, and the note is neither sent nor used as a preference. See it with `memory`; remove it with `forget design.<n>` and its exact key. To save a note send `remember` with a name, a colon and the note; `forget` and the name removes it. Spaces in the name become `-`, so `parking spot` is kept as `parking-spot`, and the note text stays as typed. For what Hass cannot do yet see [Known limits](LIMITS.md), and for every command see [the command card](COMMANDS.md).
Send (plain words): `histroy`
Send: `remember parking spot: use the back lot`
Send: `forget parking spot`
Send (plain words): `Make the product cards round`
Send: `memory`
