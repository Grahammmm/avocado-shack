# What Hass can and cannot do yet

Plain answers to "why didn't that work?". Every number on this page is checked against the code, so it stays current.

## Photos

- Send up to **4** <!-- media.MAX_PHOTOS_PER_MESSAGE --> photos per message, each a JPEG or PNG up to **20 MB** <!-- media.MAX_BYTES -->.
  Each photo gets its own code and question, and a caption sent with several photos is not read. Every photo is checked
  before any is saved: if one is refused (another picture format, too large, or unreadable), none is saved and the reply
  names which one. More than that many in one message are refused.
- Phone photos taken upright or sideways are fine; the website shows them the way they were taken.
- Voice notes are not understood yet. Please type the change instead.

## Messages

- A change request: at most **4000 characters** <!-- conversation.MAX_OWNER_TEXT --> in one message. A longer one is
  not read; send a shorter change.

## Waiting changes

- In live mode, only these changes go from chat to the website (HASS-LIVE-PLAN-1): hide or restore a product, edit a
  product's description or category (not its name), stock words, specials (no price), hikes with sign-up off (add, edit, cancel), a maker's
  about text, **a new product (HASS-LIVE-ADD-1, see the next item)**, and undo. Anything else (product names, pictures on a product that
  is already there, a brand or producer of a product that is already there, hiding or restoring a maker, the place or link of a maker that is
  already there, club details, trail facts, route ideas, sample hikes, prices, phone, address, shop hours or notice, the home page photo) is
  refused in plain words and saved for Graham to do by hand.
- **A new product goes live from chat (HASS-LIVE-ADD-1, G 2026-11-09), under these rules.** It comes with its own picture (a new
  product cannot be added without one; a picture on a product that is already there stays private). Its brand, maker line, maker name
  and town must be in your own words in this request: if one is not, Hass asks and drafts nothing, so nothing is ever filled in from a
  guess. A new maker goes live only together with the new product that names it, with its name and its town; a maker's web link is
  never put live from chat, and neither is a maker on its own. Every sentence rule below, the 10-record limit and undo still apply.
- Sentences containing origin or organic claims, health claims, awards or endorsements, trail facts, prices or
  contact details cannot be added, removed, substituted or negated. Other sentences can change; undo is allowed.
- A live change can touch at most **10** <!-- live_policy.MAX_RECORDS --> records.

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
- `photos to take` names the first **5** <!-- conversation.PHOTOS_TO_TAKE_MAX --> products that still need a photo, then says to ask again for the next few.

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

## Open requests

- When Hass asks you a question about a request, it keeps what you said (private, on the shop computer) so your short answer is read together with it. It waits **30** <!-- skills.openreq.TTL_MINUTES --> minutes after your last message, and never more than **120** <!-- skills.openreq.MAX_MINUTES --> minutes from your first one. After that, send the request again.
- Each message kept for a request is at most **4000 characters** <!-- skills.openreq.MAX_OWNER_TEXT -->, and all of them together at most **8000 characters** <!-- skills.openreq.MAX_TOTAL_TEXT -->. Once a request is finished or dropped, Hass erases those words after **24** <!-- skills.openreq.RETENTION_HOURS --> hours.
- Only you can start, answer or end a request. `no` or `cancel` drops it. If Hass still cannot tell what you mean after **3** <!-- skills.openreq.MAX_UNRESOLVED --> questions about the same thing, it stops, says so, and writes the request down.
- `backlog` shows the last **10** <!-- skills.backlog.LIST_MAX --> things Hass could not do yet. Each is kept for **90** <!-- skills.backlog.RETENTION_DAYS --> days, or until you take it off with `forget backlog.<n>`.

## Undoing a store change

- Undoing an older change to the shop details (hours, address, intro, headline, story, home photo, notice, phone or shelf check date) puts back only the details that change wrote, and keeps later edits to the other details.
- If a later edit gave one of those same details a different value, the undo is refused until that later edit is undone. A notice, with its dates, counts as one detail.
- Changes to products, hikes, makers and routes are still undone one whole item at a time.
- Weekly specials (the "This week's specials" box at the top of the page) are one saved detail: undoing an older specials change is refused if you changed the specials again after it. Undo the newer change first.
- A special shows through its last day (Pacific) and never after, even if nobody removes it. At most 6 show on one day, each runs at most 31 days, and the title and deal line are at most 60 characters with no links, email addresses or phone numbers. Only the deal line may have a price, and it appears exactly as typed.

## Several owners

- With `ownerChats` set in the config, two or more people can be owners, each in their own one-to-one chat (up to eight chats; how to
  set it up is in the connection guide, step 6). Without it there is one owner chat, as before.
- A message counts only when it comes from an owner's own address in that owner's own chat. An owner's number in another owner's chat
  is ignored, like a stranger.
- Every answer, picture and question goes to the chat the request came from. G's separate `gChat` stays text only and may never be
  an owner chat.
- A `yes` or `no` only reaches a change that the same chat asked for. If one owner tries the other's code, Hass says the change
  belongs to someone else and changes nothing.
- There is one website, so one change is open at a time. While one owner has a change waiting for a yes, waiting for details, being
  saved or going on the website, the other owner's request, photo or undo gets a plain "has a change waiting" answer and nothing is
  drafted. It works again once the first is saved, cancelled or has timed out.
- `history`, `status` and `undo` look at the whole site, so they say whose change it was ("Mike's change", "Your change"). A plain
  `undo` never takes back the other owner's change: Hass says whose it was and how to ask for it (`undo` and its code), and that is
  still only a proposal until the same owner replies `yes`.
- Pause and resume, the daily limit on new requests, the daily limit on live changes and the STOP file are shared by all owners.
  Open requests and questions are kept for each chat separately.
- The Mac forwarder takes the same list (`ownerChats` in its own config) and reads, taps back and answers in every owner chat,
  pictures included. Add the second chat to both the host settings and the forwarder config, and restart both. A forwarder that has
  not been upgraded keeps the second owner's answers waiting (nothing is sent to the wrong chat, nothing is lost).
- A change kept from before a second owner was added (everyone in one chat) can only be saved or cancelled by the person who asked
  for it; the other person is told it is not theirs and nothing changes.

## Problems log (for Graham, not for Mike)

- Hass keeps a private log of the moments where talking with Mike went wrong (it did not understand, could not do something, asked
  again, a slow reply, a reply it was not happy with, or Mike said no / that's wrong). It is kept on this machine only, in the
  `correspondence` folder inside the Hass state folder, for 90 days. It holds at most 80 characters of what Mike wrote, with
  numbers, addresses and links blanked. The state backup does not copy that folder.
- Only the numbers listed as `gSenders` in the config can ask about it. Send `problems` for the last ten, or `weekly` for the
  three most common problems with one suggested fix each; the morning report made for G adds the weekly line under it. `gSenders` is empty by default, so nothing answers until it is set; a number may not be both in `gSenders` and
  an owner number. `gChat` (G's own one-to-one chat, never Mike's chat) must be set with it: Hass answers `problems` and
  `weekly` only in that chat, as text, and ignores them anywhere else. The Mac forwarder carries that chat only when its own
  config also has the same `gChat`; at most two such answers wait at once, so they can never hold up a reply to Mike. Mike
  never sees any of this.
- `history` lines no longer show change codes, so an older change cannot be undone by code from the chat; `undo` takes back the
  last change.

## What Hass never does

- Send messages to guests or customers.
- Take payments or show prices.
- Invent organic claims, farm origins, trail facts or endorsements. If a fact is missing, Hass asks you.
- Change the public website on its own. Approved changes go to the private preview first.
