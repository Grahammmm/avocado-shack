# Owner trial (H18) - proposal

**Proposal, needs Michael and G to agree. Nothing here has been tried on Michael's phone.**

This page suggests the tasks for the owner trial in [FEATURES H18](FEATURES.md) and uses the messages from the
[phone guide](PHONE_GUIDE.md). Codes such as `a1b2` are placeholders: use the code in Hass's own reply.

## Proposed tasks

Plain-word examples use the demo catalog (Hass avocado, Linn's preserves, Etto, Cass Hill). Every change waits for
`yes <code>`; "preview" means the private preview, which only Michael and the team can see.

| # | Task | Send (example) | Success looks like |
| --- | --- | --- | --- |
| 1 | Add a product | `Add a new product called Hass avocado jam made by our own kitchen` | A draft reply with a code; after `yes a1b2`, a screenshot shows the new card and it is on the preview. |
| 2 | Edit a product | `Change the Hass avocado description to: Ripe, creamy and ready for toast` | The draft shows the old and new text; after `yes`, the screenshot shows the new description. |
| 3 | Mark availability / confirm the shelf check | `I checked the selection today: the Hass avocados are in, the Linn's blueberry preserves are sold out` | After `yes`, the preview says "Selection last checked by Michael on <day>." and the two words show on the cards. |
| 4 | Add a product photo | Send one photo, then `It is for the Hass avocado, a crate of ripe avocados on the counter` | Hass asks which product and for a few words, then drafts; after `yes`, the screenshot shows the photo upright. |
| 5 | Hide and restore a product | `Hide the Linn's blueberry preserves for now`, later `Bring back the Linn's blueberry preserves` | Each gets its own draft; after `yes`, the card is gone from the preview, then back with its photo. |
| 6 | Add or edit a maker | `Change the Etto story to: Pasta made slowly in Paso Robles` | The draft names the maker and the new text; after `yes`, the screenshot shows the maker story. |
| 7 | Change hours | `Change the opening hours to Monday to Friday 9am to 6pm and Saturday 9am to 4pm` | The draft lists the new hours line by line; after `yes`, the preview shows them. |
| 8 | Change the intro, headline or story | `Change the home page intro to: Fresh from the coast` | The draft shows the new wording; after `yes`, the screenshot shows the home page with it. |
| 9 | Create and update a hike | `Post a hike at Cass Hill on Saturday at 9am, meet at the trailhead gate`, then `Move the Cass Hill hike to 10am` | Hass asks for any missing detail, then drafts; after `yes`, the hike card on the preview shows the date, time and meeting point. |
| 10 | Cancel or mark a hike done, then add a recap | `Cancel the Cass Hill hike`, or `The Cass Hill hike is done. Recap: clear skies and a great view` | After `yes`, the preview shows the hike as cancelled, or as done with the recap text. |
| 11 | Add or edit a route idea | `Change the Cass Hill route difficulty to Easy to moderate` | The draft names the route idea; after `yes`, the screenshot shows the new wording. |
| 12 | Approve | `yes a1b2` | Hass replies that the change is saved and checked, with a screenshot. |
| 13 | Cancel | `no a1b2` | Hass replies that the draft is cancelled; the preview is unchanged. |
| 14 | Undo | `history`, then `undo a1b2`, then `yes` with the new code | `history` lists the codes; the undo draft gets a new code; after `yes`, the preview looks as it did before. |
| 15 | Status / did it work? | `status`, or `did it work?` | One reply: paused or not, waiting drafts, and a `Last change:` line saying where the last change is now. |
| 16 | Pause and resume | `pause changes`, then `yes a1b2`, then `resume changes` | Hass says changes are paused and the `yes` does not apply; after resume the draft still waits for a new `yes`. |
| 17 | Remember / forget | `remember parking: use the back lot`, `memory`, then `forget parking` | Hass confirms the note, `memory` lists it, and after `forget` it is gone; the site never changes. |
| 18 | Alias | `alias green jam: photo-product-002`, then `find green jam` | Hass confirms the alias and `find` lists Linn's triple berry preserves with its id. |
| 19 | Find | `find avocado` | A list of up to 10 matching products, makers, hikes and route ideas, each with its id. |
| 20 | Show | `show a1b2` | Hass sends that draft's text and screenshot again; nothing changes. |
| 21 | Help | `help` | A short list of every command with one example each. |

## Record form (one block per task)

Copy the form for each task tried. Result is one of: worked / did not / unclear.

```text
1. Add a product                Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
2. Edit a product               Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
3. Availability / shelf check   Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
4. Add a product photo          Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
5. Hide and restore a product   Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
6. Add or edit a maker          Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
7. Change hours                 Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
8. Intro, headline or story     Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
9. Create and update a hike     Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
10. Cancel / done / recap       Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
11. Add or edit a route idea    Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
12. Approve                     Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
13. Cancel                      Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
14. Undo                        Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
15. Status / did it work?       Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
16. Pause and resume            Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
17. Remember / forget           Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
18. Alias                       Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
19. Find                        Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
20. Show                        Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
21. Help                        Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
```

## What counts as done

FEATURES H18 says: "Michael completes at least one of each agreed task using his phone; review 7 days of normal use or
an agreed representative trial. Fix observed failures before broader use." Whether the trial is 7 days of normal use or
a shorter representative trial is Michael's and G's choice; this page does not make it.

## Not in this trial

- H07 Mac bridge check: needs the chosen Mac and Apple account, which are not set up yet.
- H11 voice notes: Hass recognises a voice note but has no speech model to turn it into text.
- H23 automatic changes: no action type has been opted in, so every change still needs `yes`.
- H24 design requests: there is no path yet from an owner request to a checked layout change.
