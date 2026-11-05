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
| 11 | Edit a route idea | `Change the Cass Hill route difficulty to Easy to moderate` | The draft names the route idea; after `yes`, the screenshot shows the new wording. |
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
| 22 | Set a home-page notice | `Put a notice on the home page saying Closed for a team meeting, through <last day>` | Replace `<last day>` with an explicit date, today or up to 60 days ahead (Pacific time); the text is at most 160 characters with at least 3 letters. A draft with a code; after `yes a1b2`, the private preview shows the one notice through that day. A second notice replaces the first. |
| 23 | Clear the home-page notice | `Clear the home-page notice` | Needs task 22 approved and its notice still present. A separate draft and `yes`; after it, the preview shows no notice. If there is none, Hass says there is no notice. |
| 24 | Set a home-page photo | Send one JPEG or PNG photo, then `Use this photo on the home page: crates of ripe avocados by the front door` | The words must describe what the photo really shows; Hass may ask for details first. After `yes`, the preview shows that one photo upright, with its description, and no location data. |
| 25 | Add a route idea | `Add a new route idea called Bluff Walk in Test Town: short and windy, 2 miles, Easy, 100 ft elevation gain, about 1 hour, a loop on packed dirt. A short test loop on the bluff. Source: Test trail guide, https://trails.example.org/bluff` | Fixture-only placeholders, not a verified trail. Hass may ask for any missing detail or the source before a draft. After `yes`, the preview lists a route idea with no date and no RSVP. |
| 26 | Hide a route idea | `Hide the Bluff Walk route idea` | Needs task 25 approved. After its own `yes`, the idea is gone from the preview's route list and nothing is deleted. |
| 27 | Bring back a route idea | `Bring back the Bluff Walk route idea` | Needs task 26 approved. After its own `yes`, the idea is back with its details and source link unchanged. |

### Notes on tasks 22-27

These six are change requests in plain words, not commands from the [command card](COMMANDS.md): Hass reads them, asks a
question if a detail is missing, and replies with a draft and its code. Nothing applies until `yes <code>`, and each
task needs its own approval. Saved means the change is on the private preview; it is not on the website until that is
copied separately (COMMANDS.md, `yes <code>`). Codes are placeholders from Hass's reply. This page does not promise the
exact words Hass will use; the operations and their offline tests back the outcomes, not a live run.

- Task 22: the last day must be today or up to 60 days ahead in Pacific time, and the text at most 160 characters with at
  least 3 letters. Hass refuses a past or too-distant day. The page drops the notice once that day is past. No promise
  is made about the public website.
- Task 23: if no notice is set, Hass replies "there is no notice" and changes nothing.
- Task 24: the words describe the photo actually sent. They are not a verified claim about the shop. A phone photo's
  rotation is kept and its location is not (COMMANDS.md, Photos).
- Task 25: the route is a made-up example. Before a real trial Michael and G replace it with their own verified route and
  source; a link is not fetched, and a web address does not prove the route's facts. A route idea is undated, takes no
  RSVPs, and is not a hike. The source must be a public https link.
- Task 26: if a scheduled hike uses the route, Hass refuses with "uses this route; change that hike first". Change that
  hike first; do not look for a way around the refusal. Hide does not delete the idea or its source.
- Task 27: a real trial uses the chosen route's own name. Restoring changes only its visibility.

Code and source for these tasks: [hass/ops/home.py](../../hass/ops/home.py) (notice and home photo),
[hass/ops/routes.py](../../hass/ops/routes.py) (route add, hide, restore), and the [command card](COMMANDS.md).

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
11. Edit a route idea           Date:            Phone/app:        Message sent:
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
22. Set a home-page notice      Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
23. Clear the notice            Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
24. Set a home-page photo       Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
25. Add a route idea            Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
26. Hide a route idea           Date:            Phone/app:        Message sent:
    Reply received (yes/no):        Result:           Notes:
27. Bring back a route idea     Date:            Phone/app:        Message sent:
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
