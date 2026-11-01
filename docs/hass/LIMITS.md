# What Hass can and cannot do yet

Plain answers to "why didn't that work?". Every number on this page is checked against the code, so it stays current.

## Photos

- Send one photo per message, as a JPEG or PNG, up to **20 MB** <!-- media.MAX_BYTES -->. Other picture formats and larger
  files are refused, and nothing is changed.
- Voice notes are not understood yet. Please type the change instead.

## Waiting changes

- A proposal or a question waits for your reply only for the time the operator has set. After that it expires and nothing
  happens; send the change again.
- One message can change at most **20** <!-- editor.MAX_OPS --> things. Split bigger jobs into several messages.

## Lists

- `history` shows the last **5** <!-- conversation.HISTORY_MAX --> changes.
- `memory` shows the first **20** <!-- conversation.MEMORY_LIST_MAX --> saved notes and says how many more there are.
- A search by name offers at most **10** <!-- ops.catalog.MAX_CANDIDATES --> matching listings; use more words to narrow it.

## Text sizes

Longer text is refused and nothing is changed; shorten it and send it again.

- Product: name **80 characters** <!-- content_model.TEXT_LIMITS[product][name] -->, brand **60 characters** <!-- content_model.TEXT_LIMITS[product][brand] -->, category **40 characters** <!-- content_model.TEXT_LIMITS[product][category] -->, description **600 characters** <!-- content_model.TEXT_LIMITS[product][description] -->, photo description **200 characters** <!-- content_model.TEXT_LIMITS[product][imageAlt] -->.
- Maker: name **80 characters** <!-- content_model.TEXT_LIMITS[maker][name] -->, place **60 characters** <!-- content_model.TEXT_LIMITS[maker][place] -->, story **600 characters** <!-- content_model.TEXT_LIMITS[maker][story] -->.
- Hike: title **80 characters** <!-- content_model.TEXT_LIMITS[event][title] -->, description **800 characters** <!-- content_model.TEXT_LIMITS[event][description] -->, meeting point **160 characters** <!-- content_model.TEXT_LIMITS[event][meetingPoint] -->, recap **2000 characters** <!-- content_model.TEXT_LIMITS[event][recap] -->, other details such as what to bring **400 characters** <!-- content_model.TEXT_LIMITS[event][bring] -->.
- Route idea: each text field **600 characters** <!-- content_model.TEXT_LIMITS[routeIdea][description] -->.
- Hiking club: name, organizer and sender **400 characters** <!-- content_model.TEXT_LIMITS[club][clubName] --> each.
- Store: street address **80 characters** <!-- content_model.TEXT_LIMITS[store][streetAddress] -->, town **80 characters** <!-- content_model.TEXT_LIMITS[store][town] -->, each line of hours **60 characters** <!-- content_model.TEXT_LIMITS[store][hoursLine] -->.
- A remembered note: at most **500 characters** <!-- memory.MAX_VALUE -->.
- A change request: at most **4000 characters** <!-- conversation.MAX_OWNER_TEXT --> in one message. A longer one is
  not read; send a shorter change.

## What Hass never does

- Send messages to guests or customers.
- Take payments or show prices.
- Invent organic claims, farm origins, trail facts or endorsements. If a fact is missing, Hass asks you.
- Change the public website on its own. Approved changes go to the private preview first.
