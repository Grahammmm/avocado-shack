# Hass on your phone: a short guide

Text Hass from Messages like you would text a helper. Nothing reaches the website until you say yes, and every change
can be undone. Codes such as `a1b2` below are placeholders: use the short code Hass puts in its own reply.

Each message stands on its own. A command (such as `status`) must be the whole message; anything else is read as a
change in plain words.

## Add a product

1. Describe the product in plain words: its name, what it is, and who makes it.
   Send (plain words): `Add a new product called Hass avocado jam made by our own kitchen`
2. Hass replies with a draft and its code, or with a question if a detail is missing. Answer the question in plain words.
3. Read the draft. When it looks right, approve it with its code.
   Send: `yes a1b2`
4. Hass replies again when the change is applied and checked.

Tip: Hass never invents organic claims or farm origins. If you want one on the page, say it in your own words.

## Add a photo

1. Send one photo on its own, as a JPEG or PNG, the right way up.
2. Hass asks which product it is for and for a few words describing the photo, and gives the draft code.
3. Answer in plain words.
   Send (plain words): `It is for the Hass avocado, a crate of ripe avocados on the counter`
4. Approve the draft with its code.
   Send: `yes a1b2`

Tip: one photo per message. A caption is never read as a command, so send any `yes` as its own message.

## Post a hike

1. Describe the hike in plain words: the trail, the date and start time, and where to meet.
   Send (plain words): `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate`
2. Hass replies with a draft and its code, or asks for any missing detail such as the meeting point.
3. Approve the draft with its code.
   Send: `yes a1b2`
4. Check upcoming hikes and their seat totals at any time.
   Send: `status`

Tip: Hass never makes up trail facts. Give it the real date and meeting point.

## Change opening hours

1. Write the new hours in plain words, one line per day or group of days.
   Send (plain words): `Change the opening hours to Monday to Friday 9am to 6pm and Saturday 9am to 4pm`
2. Hass replies with a draft and its code.
3. Approve the draft with its code.
   Send: `yes a1b2`

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

Tip: approve each draft with its code. A notice's last day is today or up to 60 days ahead (Pacific); a new notice replaces the old one, and undo removes it.

## Route ideas

1. Add an idea with its source name and link; without a source Hass asks for one.
   Send (plain words): `Add a route idea "Montana de Oro bluffs" in Los Osos: cliffs and coves, 4 miles, moderate, 250 ft elevation change, about 2 hours, a loop on dirt trail and open bluffs, described as "A loop along the bluffs with views of the coves." Source: "Park trail guide", https://example.com/mdo-bluffs`
2. Take an idea off the route list.
   Send (plain words): `Take the Cass Hill walk off the route list.`
3. Bring it back.
   Send (plain words): `Put the Cass Hill walk back on the route list.`

Tip: Hass will not hide an idea while a scheduled hike uses it; change that hike first. Approve each draft with its code.

## Undo a change

1. See the last few changes with their codes.
   Send: `history`
2. Ask for an undo of the change you want to take back, using its code.
   Send: `undo a1b2`
3. Hass replies with an undo draft and a new code. Approve it with that new code.
   Send: `yes a1b2`

Tip: an undo is a draft like any other, so nothing goes back until you say yes.

## Pause and resume

1. Stop all approvals from applying, for example while you are away.
   Send: `pause changes`
2. Check that changes are paused and see which drafts are waiting.
   Send: `status`
3. When you are ready again, let approvals apply.
   Send: `resume changes`
4. Approve any waiting draft you still want with its code.
   Send: `yes a1b2`

Tip: resuming never applies a waiting draft by itself, and drafts that wait too long expire with nothing changed.

More commands, each as its own message: `report` replies your morning shelf report, and `post photo-product-001` replies a
draft caption with the product's site photo. Neither posts anything.

Forgot a command? Send `help`. For what Hass cannot do yet see [Known limits](LIMITS.md), and for every command see
[the command card](COMMANDS.md).
