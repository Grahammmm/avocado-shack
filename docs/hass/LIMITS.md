# What Hass can and cannot do yet

Plain answers to "why didn't that work?". Every number on this page is checked against the code, so it stays current.

## Photos

- Send one photo per message, as a JPEG or PNG, up to **20 MB** <!-- media.MAX_BYTES -->. Other picture formats and larger
  files are refused, and nothing is changed.
- Phone photos taken upright or sideways are fine; the website shows them the way they were taken.
- Voice notes are not understood yet. Please type the change instead.

## Messages

- A change request: at most **4000 characters** <!-- conversation.MAX_OWNER_TEXT --> in one message. A longer one is
  not read; send a shorter change.

## Waiting changes

- A proposal or a question waits for your reply only for the time the operator has set. After that it expires and nothing
  happens; send the change again. The expiry is judged at the time you sent your reply, so a `yes` sent in time still
  counts if the shop computer handles it later.
- A reply sent more than 15 minutes after the message it answers (queued while the shop computer was offline, or a send that
  failed and was retried) starts with `Late reply to your message from <day> <time>:` so you know which message it is for.
- One message can change at most **20** <!-- editor.MAX_OPS --> things. Split bigger jobs into several messages.

## Lists

- `history` shows the last **5** <!-- conversation.HISTORY_MAX --> approved changes.
- `memory` shows the first **20** <!-- conversation.MEMORY_LIST_MAX --> saved notes and says how many more there are.
- `memory` shows the first **20** <!-- conversation.ALIAS_LIST_MAX --> aliases apart from the notes and says how many more there are.
- A search by name offers at most **10** <!-- ops.catalog.MAX_CANDIDATES --> matching listings; use more words to narrow it.
- `find` takes at most **60 characters** <!-- conversation.FIND_TEXT_MAX --> of words to look for.
- An alias name is at most **60 characters** <!-- conversation.ALIAS_NAME_MAX -->.

## Text sizes

Longer text is refused and nothing is changed; shorten it and send it again.

- Product: name **80 characters** <!-- content_model.TEXT_LIMITS[product][name] -->, brand **60 characters** <!-- content_model.TEXT_LIMITS[product][brand] -->, category **40 characters** <!-- content_model.TEXT_LIMITS[product][category] -->, description **600 characters** <!-- content_model.TEXT_LIMITS[product][description] -->, photo description **200 characters** <!-- content_model.TEXT_LIMITS[product][imageAlt] -->.
- Maker: name **80 characters** <!-- content_model.TEXT_LIMITS[maker][name] -->, place **60 characters** <!-- content_model.TEXT_LIMITS[maker][place] -->, story **600 characters** <!-- content_model.TEXT_LIMITS[maker][story] -->.
- Hike: title **80 characters** <!-- content_model.TEXT_LIMITS[event][title] -->, description **800 characters** <!-- content_model.TEXT_LIMITS[event][description] -->, meeting point **160 characters** <!-- content_model.TEXT_LIMITS[event][meetingPoint] -->, recap **2000 characters** <!-- content_model.TEXT_LIMITS[event][recap] -->, other details such as what to bring **400 characters** <!-- content_model.TEXT_LIMITS[event][bring] -->.
- Route idea: each text field **600 characters** <!-- content_model.TEXT_LIMITS[routeIdea][description] -->.
- Hiking club: name, organizer and sender **400 characters** <!-- content_model.TEXT_LIMITS[club][clubName] --> each.
- Store: street address **80 characters** <!-- content_model.TEXT_LIMITS[store][streetAddress] -->, town **80 characters** <!-- content_model.TEXT_LIMITS[store][town] -->, each line of hours **60 characters** <!-- content_model.TEXT_LIMITS[store][hoursLine] -->, at most **7** <!-- content_model.MAX_HOURS_LINES --> lines of hours.
- A remembered note: at most **500 characters** <!-- memory.MAX_VALUE -->; spaces in its name become `-`, and the stored name stays 1-64 of a-z, 0-9, `.` or `-`.

## Phone and prices

- The store phone is a US number of **10 digits** <!-- ops.store.PHONE_DIGITS --> (spaces, dashes and brackets are fine); anything else is refused.
- A purchase cost (`cost`, `margin`) is private and up to **100000 dollars** <!-- margins.PACK_COST_MAX --> for **1** <!-- margins.UNITS_MIN -->–**10000** <!-- margins.UNITS_MAX --> units.

## Home page

- Intro: at most **160 characters** <!-- content_model.MAX_INTRO -->.
- Headline: each line at most **40 characters** <!-- content_model.MAX_HEADLINE_LINE -->.
- Story: at most **400 characters** <!-- content_model.MAX_STORY -->.
- Notice: at most **160 characters** <!-- content_model.MAX_NOTICE -->; its last day can be today or up to **60** <!-- content_model.MAX_NOTICE_DAYS --> days ahead.
- Home photo: JPEG or PNG, up to **20 MB** <!-- media.MAX_BYTES -->.
- The home photo needs a real description of at least three letters; a file name like IMG_1234 is refused.

## Undoing a store change

- Undoing an older change to the shop details (hours, address, intro, headline, story, home photo, notice, phone or shelf check date) puts back only the details that change wrote, and keeps later edits to the other details.
- If a later edit gave one of those same details a different value, the undo is refused until that later edit is undone. A notice, with its dates, counts as one detail.
- Changes to products, hikes, makers and routes are still undone one whole item at a time.

## What Hass never does

- Send messages to guests or customers.
- Take payments or show prices.
- Invent organic claims, farm origins, trail facts or endorsements. If a fact is missing, Hass asks you.
- Change the public website on its own. Approved changes go to the private preview first.
