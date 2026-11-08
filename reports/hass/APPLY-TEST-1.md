# HASS-APPLY-TEST-1: apply, undo and failure cases through the real chat path, on a scratch copy

Cards t_54fda9c4 (first run) and t_d877c651 (this run) · repo Grahammmm/avocado-shack · code under test: `main` 0a8114c (after PR #527) · run 2026-11-08 afternoon PST. **Reviewed: no. Merged: no. Verified = I ran it and saw the output.**

## What was run (all scratch; nothing live touched)

- **Real path (first scratch):** a clone of the site at 0a8114c, a writer worktree (branch `hass/scratch-live`), a scratch state folder and key, the real `hass/host.py serve` on **127.0.0.1:18796** (not 8795) and the real `hass/host.py work` with `approvals: private`, previewer on, pictures on, interpreter = the GPU router (`qwen3.8:27b-thinkingcap-q6`, `api openai`, no CPU fallback). Synthetic owner messages (`owner@example.invalid`) were sealed and posted the way the Mac forwarder does; replies and phone pictures were pulled back through the scratch relay. Every apply/undo was followed by the writer's own `sitegen --check` and `migration_check` (exit codes) and a meaning-level diff (JSON parsed, key order ignored) against the pre-change tree.
- **In-process injections (second scratch clone):** the real `Conversation` + production `Editor` + real `Previewer`, one writer worktree and state folder per case, because an editor error halfway and a failing preview need a code hook. Interpreter: fixture (exact text to ops) for injections; the real GPU interpreter for specials and the photo cases.
- **Not touched:** live state, live writer, `host.json`, port 8795, the Mac, any real message, any service. The previewer ran: Playwright plus the headless Chromium already on the box (no Node limit hit).

## The three most important findings (plain words)

1. **Weekly specials cannot be added or edited from chat.** The interpreter's own check does not know the "deal" kind of detail, so every attempt answers "I need a detail as words. Could you say it another way?" and "take the special off" cannot find a special because the prompt never lists any. With a one-line fix (applied in memory only) the add works, but the draft then reads "Avocado Shack, a detail: from nothing to more than I can show here", so Mike cannot see what he is approving.
2. **Undo is not a real revert.** It is a new edit that rewrites the record. For hide, restore, stock and hike time the files differ in bytes after apply+undo (same meaning); undo of an added hike leaves it on the page as cancelled, undo of an added maker leaves a hidden maker, undo of an added product leaves a hidden product and its picture file. Only plain edits (description, place, hike cancel) undo to an identical tree.
3. **A crash halfway is clean only after a restart, and private mode lets claims through.** If the editor fails after writing the first file, the file stays half-changed, the draft stays "approved", Mike gets no reply (and `status` says nothing is waiting) until the worker restarts; then it says "interrupted and not saved" and the tree is clean. Separately, in private mode "certified organic, grown at our own farm" was drafted and would be applied (the live-policy refusal only runs in `live` mode). Also: the real worker refuses all photos, so a new item with a picture cannot be done through chat today.

What works: every skill in the table applies through the real chat with a draft, a diff, a signed-off writer commit, passing checks and a truthful reply; pause, expiry, strangers, two drafts waiting, risky edits and a failing build all behave safely.

## Scenario table (real worker, scratch, private mode)

| Skill | Owner message | Code in draft | Apply commit | Checks after apply | Undo commit | Checks after undo | Tree after undo vs before |
|---|---|---|---|---|---|---|---|
| Item hide | `Hide the lemons` | code shown | `20a7cdf` | pass | `1c38b75` | pass | differs in bytes only |
| Item restore | `Bring the cashews back on the site` | no code | `657cd34` | pass | `83685cc` | pass | differs in bytes only (products.json) |
| Item edit | `The lemons description should say they are great in cocktails` | no code | `1531f77` | pass | `2ae9579` | pass | byte-identical |
| Maker edit | `Stepladder is based in Paso Robles, not Cambria` | no code | `29ae7d4` | pass | `c9ac6e0` | pass | byte-identical |
| Maker add | `Add a new maker: Morro Bay Salsa Co., based in Morro Bay, California.  ...` | no code | `a55d8a0` | pass | `21c5830` | pass | maker stays in makers.json, hidden |
| Maker hide (with its product) | `Hide the maker Taco Works` | no code | `2dcb6ee` | pass | `d1857b0` | pass | differs in bytes only |
| Sold out + shelf check | `The Hass avocado is sold out today` | no code | `d6e4bc9` | pass | `5a0f0f1` | pass | differs in bytes only |
| Hike add | `Add a hike: Montaña de Oro Sunrise Walk, Saturday December 5th at 8am. ...` | no code | `21eb096` | pass | `b18a79b` | pass | hike stays on the page as cancelled |
| Hike edit | `Push the Morro Rock Beach Stroll back to 10am, the tide is lower later` | no code | `b3bc3f3` | pass | `5f164ab` | pass | differs in bytes only |
| Hike cancel | `Cancel the Morro Rock Beach Stroll, it's going to rain` | no code | `612ce4e` | pass | `1ba07d9` | pass | byte-identical |

### Item hide (`s1a-hide`)

Owner: `Hide the lemons`

Draft shown:
```
Here's the change I'd make:
Lemons, whether it shows: from showing to hidden
I'll hold this for you until today at 2:13 pm.
Reply yes 06c87e to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `0a8114c`): `20a7cdf` 20a7cdf hass content: chg-06c87e122987

```diff
diff --git a/hass/content/products.json b/hass/content/products.json
index 62d54a4..5e0f907 100644
--- a/hass/content/products.json
+++ b/hass/content/products.json
@@ -33,5 +33,5 @@
       "producerKey": null,
       "displayBrand": "From the market",
-      "status": "active"
+      "status": "hidden"
     },
     {
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: whether it shows for Lemons
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Lemons, whether it shows: from hidden to showing
I'll hold this for you until today at 2:14 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `1c38b75`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `null` (differs in bytes only).

### Item restore (`s1b-restore`)

Owner: `Bring the cashews back on the site`

Draft shown:
```
Here's the change I'd make:
Cashews, whether it shows: from hidden to showing
I'll hold this for you until today at 2:15 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `dff4c62`): `657cd34` 657cd34 hass content: chg-b435bc92e948

```diff
diff --git a/hass/content/products.json b/hass/content/products.json
index 4547fcd..a242794 100644
--- a/hass/content/products.json
+++ b/hass/content/products.json
@@ -1243,5 +1243,5 @@
       "producerKey": null,
       "displayBrand": "Avocado Shack",
-      "status": "hidden"
+      "status": "active"
     },
     {
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: whether it shows for Cashews
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Cashews, whether it shows: from showing to hidden
I'll hold this for you until today at 2:16 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `83685cc`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/products.json"], "meaning": []}` (differs in bytes only (products.json)).

### Item edit (`s1c-edit`)

Owner: `The lemons description should say they are great in cocktails`

Draft shown:
```
Here's the change I'd make:
Lemons, the description:
  was: Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own bus...
  now: Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own business for hours. They are also great in cocktails.
I'll hold this for you until today at 2:16 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `83685cc`): `1531f77` 1531f77 hass content: chg-b4821d29133f

```diff
diff --git a/hass/content/products.json b/hass/content/products.json
index e1f756c..f51a23c 100644
--- a/hass/content/products.json
+++ b/hass/content/products.json
@@ -27,5 +27,5 @@
       "brand": "Producer not identified",
       "category": "fruit",
-      "description": "Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own business for hours.",
+      "description": "Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own business for hours. They are also great in cocktails.",
       "displayBrand": "From the market",
       "id": "photo-product-017",
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: the description for Lemons
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Lemons, the description:
  was: Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own bus...
  now: Not an afterthought. A squeeze of lemon can wake up fish, greens, or a pot of beans that has been minding its own business for hours.
I'll hold this for you until today at 2:16 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `2ae9579`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": [], "meaning": []}` (byte-identical).

### Maker edit (`s2a-maker-edit`)

Owner: `Stepladder is based in Paso Robles, not Cambria`

Draft shown:
```
Here's the change I'd make:
Stepladder, the place: from Cambria, California to Paso Robles
Heads up: This changes the 'Based in' line on 8 product cards.
I'll hold this for you until today at 2:17 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `2ae9579`): `29ae7d4` 29ae7d4 hass content: chg-ce104e1e4c8d

```diff
diff --git a/hass/content/makers.json b/hass/content/makers.json
index 94272f2..8ed42ee 100644
--- a/hass/content/makers.json
+++ b/hass/content/makers.json
@@ -10,5 +10,5 @@
     "Stepladder": {
       "name": "Stepladder",
-      "place": "Cambria, California",
+      "place": "Paso Robles",
       "story": "There is a real ranch behind this cheese. Stepladder makes its cheeses in a restored barn in the hills of Cambria, with LaMancha goats grazing on the property. Place, milk and the patient work of cheesemaking meet here. Slice it, share it, and let it come to the table.",
       "url": "https://stepladdercreamery.com/pages/farm"
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: the place for Stepladder
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Stepladder, the place: from Paso Robles to Cambria, California
I'll hold this for you until today at 2:17 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `c9ac6e0`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": [], "meaning": []}` (byte-identical).

### Maker add (`s2b-maker-add`)

Owner: `Add a new maker: Morro Bay Salsa Co., based in Morro Bay, California. They make small batch salsas. Their website is https://example.com/salsa`

Draft shown:
```
Here's the change I'd make:
A new maker: Morro Bay Salsa Co.
  the name: Morro Bay Salsa Co.
  the place: Morro Bay, California
  the story: They make small batch salsas.
  the website link: https://example.com/salsa
I'll hold this for you until today at 2:17 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `c9ac6e0`): `a55d8a0` a55d8a0 hass content: chg-1b99f13dedf8

```diff
diff --git a/hass/content/makers.json b/hass/content/makers.json
index 94272f2..c6b289f 100644
--- a/hass/content/makers.json
+++ b/hass/content/makers.json
@@ -157,4 +157,10 @@
       "story": "Ava’s Keitt mangoes are identified by its distributor as California fruit grown in the Coachella Valley. Keitts can stay green when ripe; a gentle give is a better clue than color. Cut into one and let the smooth golden flesh do the convincing.",
       "url": "https://static1.squarespace.com/static/61d88f5cc75725423dd78068/t/6300fad4761f1941541aedaf/1661008598041/Earls_KeittMangosPOS.pdf"
+    },
+    "Morro Bay Salsa Co.": {
+      "name": "Morro Bay Salsa Co.",
+      "place": "Morro Bay, California",
+      "story": "They make small batch salsas.",
+      "url": "https://example.com/salsa"
     }
   }
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: a new maker: Morro Bay Salsa Co.
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Morro Bay Salsa Co., whether it is hidden: from nothing to yes
I'll hold this for you until today at 2:18 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `21c5830`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/makers.json"], "meaning": ["hass/content/makers.json"]}` (maker stays in makers.json, hidden).

### Maker hide (with its product) (`s2c-maker-hide-busy`)

Owner: `Hide the maker Taco Works`

Draft shown:
```
Here's the change I'd make:
Taco Works, whether it is hidden: from nothing to yes
Montaña de Oro Sea Salt tortilla chips, whether it shows: from showing to hidden
I'll hold this for you until today at 2:18 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `21c5830`): `2dcb6ee` 2dcb6ee hass content: chg-579355c66564

```diff
diff --git a/hass/content/makers.json b/hass/content/makers.json
index d224291..9452fef 100644
--- a/hass/content/makers.json
+++ b/hass/content/makers.json
@@ -108,5 +108,6 @@
       "place": "San Luis Obispo, California",
       "story": "Taco Works started as a San Luis Obispo restaurant in 1976. Its tortilla chips became popular enough to outgrow the restaurant and become a business of their own. The Montaña de Oro line keeps things straightforward: white corn and salt. Give them a good bowl of guacamole.",
-      "url": "https://www.tacoworks.net/pages/about-us"
+      "url": "https://www.tacoworks.net/pages/about-us",
+      "hidden": true
     },
     "Maple Valley": {
diff --git a/hass/content/products.json b/hass/content/products.json
index e1f756c..deb20a1 100644
--- a/hass/content/products.json
+++ b/hass/content/products.json
@@ -154,5 +154,5 @@
       "producerKey": "Taco Works",
       "displayBrand": "Taco Works",
-      "status": "active"
+      "status": "hidden"
     },
     {
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: whether it is hidden for Taco Works; whether it shows for Montaña de Oro Sea Salt tortilla chips
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Taco Works, whether it is hidden: from yes to nothing
Montaña de Oro Sea Salt tortilla chips, whether it shows: from hidden to showing
I'll hold this for you until today at 2:19 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `d1857b0`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/products.json", "storefront-mockup/catalog-products.js"], "meaning": []}` (differs in bytes only).

### Sold out + shelf check (`s3-stock`)

Owner: `The Hass avocado is sold out today`

Draft shown:
```
Got it. This draft also records that the shelf list was checked today.
Here's the change I'd make:
Avocado Shack, the shelf check: from nothing to 2026-11-08
Hass avocado, the shelf word: from nothing to no
Hass avocado, when it was last checked: from nothing to 2026-11-08
I'll hold this for you until today at 2:19 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `d1857b0`): `d6e4bc9` d6e4bc9 hass content: chg-a42f224de1d2

```diff
diff --git a/hass/content/products.json b/hass/content/products.json
index edff388..ac34b1a 100644
--- a/hass/content/products.json
+++ b/hass/content/products.json
@@ -11,5 +11,7 @@
       "producerKey": null,
       "displayBrand": "Avocado Shack",
-      "status": "active"
+      "status": "active",
+      "available": "no",
+      "available_on": "2026-11-08"
     },
     {
diff --git a/hass/content/store.json b/hass/content/store.json
index bc809cd..ceadf55 100644
--- a/hass/content/store.json
+++ b/hass/content/store.json
@@ -7,4 +7,5 @@
     "Monday–Friday 9am–6pm",
     "Saturday 9am–5pm · Closed Sunday"
-  ]
+  ],
+  "selection_checked_on": "2026-11-08"
 }
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: the shelf check for Avocado Shack; the shelf word, when it was last checked for Hass avocado
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Avocado Shack, the shelf check: from 2026-11-08 to nothing
Hass avocado, the shelf word: from no to nothing
Hass avocado, when it was last checked: from 2026-11-08 to nothing
I'll hold this for you until today at 2:19 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `5a0f0f1`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/products.json", "storefront-mockup/catalog-products.js"], "meaning": []}` (differs in bytes only).

### Hike add (`s4a-hike-add`)

Owner: `Add a hike: Montaña de Oro Sunrise Walk, Saturday December 5th at 8am. Meet at the Spooners Cove parking lot. Easy difficulty. A gentle sunrise stroll along the bluffs with ocean views. No sign-ups needed.`

Draft shown:
```
Here's the change I'd make:
A new hike: Montaña de Oro Sunrise Walk
  the description: A gentle sunrise stroll along the bluffs with ocean views.
  how hard it is: easy
  the meeting place: Spooners Cove parking lot
  whether guests can sign up: no
  the start time: Saturday, Dec 5 at 8 am
  whether it shows: scheduled
  the title: Montaña de Oro Sunrise Walk
I'll hold this for you until today at 2:20 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `5a0f0f1`): `21eb096` 21eb096 hass content: chg-10a8a942801b

```diff
diff --git a/hass/content/community.json b/hass/content/community.json
index 467308a..332fd37 100644
--- a/hass/content/community.json
+++ b/hass/content/community.json
@@ -7,5 +7,17 @@
     "emailConnected": false
   },
-  "events": [],
+  "events": [
+    {
+      "id": "hike-2026-12-05-montana-de-oro-sunrise-walk",
+      "title": "Montaña de Oro Sunrise Walk",
+      "startsAt": "2026-12-05T08:00:00-08:00",
+      "timezone": "America/Los_Angeles",
+      "status": "scheduled",
+      "meetingPoint": "Spooners Cove parking lot",
+      "difficulty": "easy",
+      "description": "A gentle sunrise stroll along the bluffs with ocean views.",
+      "rsvpEnabled": false
+    }
+  ],
   "routeIdeas": [
     {
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: a new hike: Montaña de Oro Sunrise Walk
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Montaña de Oro Sunrise Walk, whether it shows: from scheduled to cancelled
I'll hold this for you until today at 2:20 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `b18a79b`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/community.json", "storefront-mockup/community.json"], "meaning": ["hass/content/community.json", "storefront-mockup/community.json"]}` (hike stays on the page as cancelled).

### Hike edit (`s4c-hike-edit`)

Owner: `Push the Morro Rock Beach Stroll back to 10am, the tide is lower later`

Draft shown:
```
Here's the change I'd make:
Morro Rock Beach Stroll, the start time: from Saturday, Dec 12 at 9 am to Saturday, Dec 12 at 10 am
I'll hold this for you until today at 2:21 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `8859df1`): `b3bc3f3` b3bc3f3 hass content: chg-7a96343ea5c9

```diff
diff --git a/hass/content/community.json b/hass/content/community.json
index 03dd1bc..4e77079 100644
--- a/hass/content/community.json
+++ b/hass/content/community.json
@@ -22,5 +22,5 @@
       "id": "hike-2026-12-12-morro-rock-beach-stroll",
       "title": "Morro Rock Beach Stroll",
-      "startsAt": "2026-12-12T09:00:00-08:00",
+      "startsAt": "2026-12-12T10:00:00-08:00",
       "timezone": "America/Los_Angeles",
       "status": "scheduled",
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: the start time for Morro Rock Beach Stroll
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Morro Rock Beach Stroll, the start time: from Saturday, Dec 12 at 10 am to Saturday, Dec 12 at 9 am
I'll hold this for you until today at 2:21 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `5f164ab`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": ["hass/content/community.json", "storefront-mockup/community.json"], "meaning": []}` (differs in bytes only).

### Hike cancel (`s4d-hike-cancel`)

Owner: `Cancel the Morro Rock Beach Stroll, it's going to rain`

Draft shown:
```
Here's the change I'd make:
Morro Rock Beach Stroll, the cancellation note: from nothing to It's going to rain
Morro Rock Beach Stroll, whether it shows: from scheduled to cancelled
I'll hold this for you until today at 2:21 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Writer commit after `yes` (base `5f164ab`): `612ce4e` 612ce4e hass content: chg-011a3dc9d571

```diff
diff --git a/hass/content/community.json b/hass/content/community.json
index b1d9731..dfe4c14 100644
--- a/hass/content/community.json
+++ b/hass/content/community.json
@@ -26,7 +26,8 @@
       "rsvpEnabled": false,
       "startsAt": "2026-12-12T09:00:00-08:00",
-      "status": "scheduled",
+      "status": "cancelled",
       "timezone": "America/Los_Angeles",
-      "title": "Morro Rock Beach Stroll"
+      "title": "Morro Rock Beach Stroll",
+      "cancelNote": "It's going to rain"
     }
   ],
```

Checks after apply: {"sitegen --check": 0, "migration_check": 0} (exit codes).

Reply after `yes`:
```
Saved and checked: the cancellation note, whether it shows for Morro Rock Beach Stroll
It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
```

Reply to `undo` (the undo draft):
```
To undo that, I'd change it back:
Here's the change I'd make:
Morro Rock Beach Stroll, the cancellation note: from It's going to rain to nothing
Morro Rock Beach Stroll, whether it shows: from cancelled to scheduled
I'll hold this for you until today at 2:21 pm.
Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.
```

Undo commit `1ba07d9`; checks {"sitegen --check": 0, "migration_check": 0}; tree vs the pre-change base: `{"bytes": [], "meaning": []}` (byte-identical).

## In-process failure injections (second scratch clone; real Conversation + production Editor + real Previewer)

Nothing here touches the first scratch or anything live. Each case has its own writer worktree and state folder. Harness: `ip.py` in this card's workspace (not committed; it is a scratch driver).

### I1. Editor error halfway (first changed file written, then `OSError: No space left on device`)

  - owner `Hide the figs` -> proposed; reply: (none)
  - owner `yes` -> EXCEPTION OSError: [Errno 28] No space left on device (simulated); reply: (none)
  - owner `yes` -> no-target; reply: Nothing is waiting for your yes.
  - owner `status` -> status; reply: Everything is ready. Nothing is waiting for your yes. I still need your shelf check.
  - owner `Hide the figs` -> proposed; reply: (none)
  - owner `yes` -> approved; reply: Saved and checked: whether it shows for Figs It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.

State right after the failed `yes` (verified from git and the state folder):

```json
{
 "head": "0a8114c",
 "status": [
  "M hass/content/products.json"
 ],
 "journal": [
  "chg-2445adcb6dd3.json"
 ],
 "changes": [],
 "drafts": [
  {
   "code": "2445",
   "state": "approved",
   "summary": "whether it shows for Figs",
   "reason": null,
   "commit": ""
  }
 ]
}
```

After a worker restart (`Conversation.recover()`): That change was interrupted and not saved. The website is as it was before. Please send it again. Worktree status `[]`, head `0a8114c` (unchanged), draft state `failed`, journal gone. **Result: nothing is left half-applied after recovery, but until the worker restarts the file is half-changed, the draft sits `approved`, the owner gets no reply at all, and `status` says "Everything is ready. Nothing is waiting for your yes."**

### I1b. Same error, then the owner sends a different change before any restart

  - owner `Hide the figs` -> proposed; reply: (none)
  - owner `yes` -> EXCEPTION OSError: [Errno 28] No space left on device (simulated); reply: (none)
  - owner `Hide the blackberries` -> proposed; reply: (none)
  - owner `yes ef3e` -> approved; reply: The website changed while that was waiting, so I've written it up again. Please look it over: Here's the change I'd make: Blackberries, whether it shows: from showing to hidden I'll hold this for you until today at 3 pm. Reply yes to save it, or no to cancel.  ...

The next apply runs the editor's own recovery first, which restores the file, so nothing stays half-written. But the second draft had been prepared on the half-written file, so its `yes` was answered with "The website changed while that was waiting, so I've written it up again" (a false reason) and needed another `yes`. The first draft (`2445`) stays `approved` forever and its owner is never told.

### I2. Build/commit fails after the edit

Two variants. (a) a real git failure: a pre-commit hook in this scratch writer refuses the commit after the files were written and the checks passed. (b) the editor's post-apply check reports a stale generated file (simulated by patching `_post_checks` for this one call).

- (a) hook:   - owner `yes` -> approved; reply: I couldn't save that change, so nothing changed. Please try again, or ask Graham if it keeps happening.
  After: head `0a8114c` (unchanged), status `[]`, worktree diff vs HEAD `empty`, draft state `failed` (reason `git commit failed`).
- (b) check:   - owner `yes` -> approved; reply: I couldn't save that change, so nothing changed. Please try again, or ask Graham if it keeps happening.
  After: head `0a8114c` (unchanged), status `[]`, worktree diff empty, draft `failed`; a second `yes` answers "Nothing is waiting for your yes."

**Result: pass.** The change is not left applied and the reply says plainly that nothing changed.

### I3. Previewer fails after the commit (result screenshot)

  - owner `Hide the figs` -> proposed; reply: (none)
  - owner `yes` -> approved; reply: I saved it, but the preview check didn't pass: I couldn't check the preview. It's saved, but not on the website yet. Copying it there is a separate step. Please ask Graham to put it on the website.
  - owner `status` -> status; reply: Everything is ready. Nothing is waiting for your yes. I still need your shelf check. Last change: whether it shows for Figs. It's saved, but I'm not sure it's on the website. The preview check didn't pass: I couldn't check the preview. If copying it started an ...

After: head `d380f3b` (1 commit ahead), draft state `applied`, reason `not verified: products photo-product-097: browser failed to start (simulated)`. **The change stays committed on the writer branch**; the reply says "I saved it, but the preview check didn't pass" (true). The `status` wording then talks about copying to the website, which does not apply in private mode.

### I4. Weekly specials, add and remove (kind fix applied in memory only)

Add through the real GPU interpreter (`interpret_check.STRING_KINDS` + `deal` in memory): draft, `yes`, `sitegen --check` ok, undo, `yes` all worked. Draft text the owner sees: **"Avocado Shack, a detail: from nothing to more than I can show here"** (title, deal and last day are not shown). The interpreter also invented `product: photo-product-097` (a link to the Figs product). Remove (fixture interpreter, because the real prompt lists no specials): `specials.remove` applied, undo restored the special; the tree after undo differs from before the remove only in key order (`store.json`).

```diff
a/hass/content/store.json b/hass/content/store.json
index bc809cd..9f70be3 100644
--- a/hass/content/store.json
+++ b/hass/content/store.json
@@ -8,2 +8,13 @@
     "Saturday 9am–5pm · Closed Sunday"
+  ],
+  "specials": [
+    {
+      "id": "fresh-figs",
+      "title": "Fresh Figs",
+      "deal": "2 for 1",
+      "start": "2026-11-08",
+      "end": "2026-11-15",
+      "order": 0,
+      "product": "photo-product-097"
+    }
   ]
```

### I5. New item with a test picture

- Real worker: every photo is refused ("I can't read photos, voice notes or files yet"); `Conversation(photos=None)` in `host.py`.
- In-process with a photo source and the real interpreter (3 variants, `c5`, `c5b`, `c5c`): the photo opens the question "Which product is this photo for..."; the follow-up with the product details was never turned into a `product.add` with the photo ("Send the photo with the product name as its caption.", "That doesn't look quite right.", or a repeated maker question). Not completed through the interpreter.
- Apply side only (`c5d`, fixture interpreter supplying `product.add` with the stored photo): draft listed the new product, `yes` -> commit adds `products.json` (13 lines), `catalog-products.js` and `assets/products/photo-79a8f16c7269f43b.jpg` (206-byte original JPEG, no 800x800 WebP), `sitegen --check` ok (171 active products); undo -> the product stays in `products.json` as `hidden` and the image file stays. The draft also lists the name twice.


## Failure cases through the real worker (scratch, port 18796)

| Case | Messages | Result |
|---|---|---|
| Apply when paused | `pause changes`, `Hide the figs`, `yes`, `status`, `resume changes`, `yes` | Draft carries "Changes are paused, so nothing will be saved yet." `yes` while paused: "Changes are paused, so I haven't saved that. Say resume changes, then reply yes 9f02." **No commit.** `resume changes` lists the waiting code; `yes` then applies (commit ad2861a). Pass. |
| Apply after expiry (TTL 120 s) | `Hide the guacamole`, wait 125 s, `yes`, `yes 0000` | "That change timed out today at 2:26 pm, so nothing changed. Tell me again if you still want it." / "I don't have a change with that code." No commit. Pass. |
| A stranger says yes | stranger sends `yes`, `yes <code>` (owner chat and own chat), a new request | All four: disposition `ignored`, no reply, no draft state change, no commit. Pass. |
| Two drafts waiting | `Hide the figs`, `Hide the blackberries`, `yes`, `yes 9db8`, `no` | Bare `yes`: "Which one do you mean? Reply yes or no and its code." with both codes. `yes 9db8` applies only the figs (1 commit). Bare `no` cancels the remaining one. Pass. (Both drafts say "Reply yes to save it" without a code; the code appears only when asked.) |
| Risky edits | raw-milk cheese, a price, an organic claim, hide all vegetables, delete everything, injection with phone and email | Cheese: asks which one (no hold wording). Price: refused politely. **Organic claim: drafted** (private mode only; finding 3). Hide all: asks which 6 (cap 6). Delete everything: asks, offers a hide. Injection: "I can only publish changes you approve one at a time. Nothing was changed." No commits made. |
| New item with a picture | empty text + photo; photo + caption | "I can't read photos, voice notes or files yet, so nothing changed. Could you type the change instead?" Refused, no draft. |
| Editor error halfway, build fails after the edit, preview fails after the commit | in-process | See the injection section below. |

Other observations from the real path (first run): the first proposal of a draft shows no code ("Reply yes to save it"); a repeat of an expired or cancelled draft shows a code and a bare `yes` is refused ("That is the same change that was cancelled earlier, so I want to be sure"). "Take the lemons off the site please, we ran out for the season" was read as sold out and started the shelf-check question, not a hide. "Hide the lemons" while a draft for lemons waited answered "It already says that: Lemons is hidden", which was untrue (nothing was hidden yet). Two stock drafts showed a computer date ("from nothing to 2026-11-08").

## Phone pictures (looked at with the image tool)

| Scenario | Does the picture show the change? |
|---|---|
| Hide figs / hide lemons (draft) | Yes: the shop page filtered to the name shows "0 selections · 0 shown" (the item is gone). |
| Edit lemons description | Yes: the Lemons card with "They are also great in cocktails." |
| Maker edit (Stepladder place) | **No**: shows other makers (Etto, "Based in Paso Robles") further down the page. |
| Maker add (Morro Bay Salsa Co.) | **No**: shows neighbouring coffee listings. |
| Hike add / edit | **No**: shows the top of the Hiking Club page; the hike list is below the shot (as E2E-HIKE-1 found). |
| Stock (Hass avocado sold out) | **No**: shows the bottom of the home page (about the market and newsletter). |

## Voice check (docs/hass/VOICE.md, `voice.check`, long text allowed)

- 87 replies delivered through the real worker in the first run: 83 clean; 4 flagged: two stock drafts carrying a computer date, a 6 to 8 character repeat code that trips the long-code rule (allowed after a `yes`), and one quoted owner text. The service's own check did not replace the date ones (no safe line), so it misses a date inside a draft.
- This run, 20 fixed replies (held, not-read, photo question, fetch failed, under way, unknown state, not-live, live unknown/unconfirmed, route unshown, recovered, and the live-policy refusals for each kind): **0 flagged.**
- In-process replies I read (all cases): 1 flagged, the claim question that shows raw field names ("brand" and "displayBrand", voice rule "a name written like startsAt") and was still delivered.

## Private-mode live test plan (operator steps; do not run until G/the operator says go)

Goal: Mike's `yes` applies a change to the **writer branch only**; nothing goes on the website. Read-only first, then one flip, then the test messages, then the revert.

**Before (nothing changes):**
1. Read the units to learn the real paths: `systemctl --user cat hass-worker` (the `--host <host.json>` path; writer is `~/.local/share/hass/writer`, branch `hass/live`, runtime `~/.local/share/hass/runtime`).
2. `python3 hass/host.py check --host <host.json>` and `python3 hass/health.py --host-dir <dir>` both clean; `systemctl --user status hass-receiver hass-worker`.
3. Record the base: `git -C ~/.local/share/hass/writer rev-parse HEAD` (call it BASE) and `git -C ~/.local/share/hass/writer status --porcelain` (must be empty). Write BASE in the test notes.
4. Backup: `python3 hass/statebackup.py create`, then `python3 hass/statebackup.py verify <backup>`.
5. Extra stop for publishing: `touch ~/.config/hass/STOP` (stops all live publishing; the chat keeps answering). Keep it in place for the whole test.
6. Tell Mike first: replies will end "It's saved, but not on the website yet. Please ask Graham." and that is correct.

**Flip (operator, one restart):**
7. Edit only the `"approvals"` value in the live `host.json` from `"hold"` to `"private"`. Leave every other key as it is (state, secretFile, listen, allowedPeers, previewer, pictures, runtimeCommit, interpreter). `host.py check` again.
8. `systemctl --user restart hass-worker` (the receiver only stores and never applies, so it does not need a restart). Confirm the worker is running and `health.py` is clean.

**Messages Mike (or the operator on Mike's phone) sends, in this order. Each: read the draft, send `yes` (or the code if asked), then look at the reply, then `undo` and `yes`:**
a. `status` (one reply, no change).
b. `Hide the lemons` -> draft shows "Lemons ... from showing to hidden" and a picture; `yes`; `undo`; `yes`.
c. `The lemons description should say they are great in cocktails` -> `yes` -> `undo` -> `yes`.
d. A maker edit that is true on the real site, then undo.
e. `The Hass avocado is sold out today` -> answer `yes` to the shelf-check question -> `yes` on the draft -> `undo`.
f. A hike: `Add a hike: <name>, <a real future date and time>, ...` -> `yes`; then `Push it back to <time>`; then `Cancel it`. (Use a clearly marked test name.) Undo leaves the hike as cancelled, so it must be cleaned by the revert step below.
g. `pause changes`, `Hide the figs`, `yes` (must not apply), `resume changes`, `yes`.
h. Two drafts: `Hide the figs`, `Hide the blackberries`, bare `yes` (expect the code list), `yes <code>`, `no`.
i. Let one draft sit past its expiry, then `yes` (expect "timed out").
**Do not send in this test (known defects, see follow-ups):** weekly specials, a photo or new item with a picture, any statement of origin/organic/health/award/phone/email (private mode does not run the live-policy check), "take X off ... we ran out" (can mean sold out).

**What to inspect after each step (read-only):**
- `git -C ~/.local/share/hass/writer log --oneline BASE..HEAD` and `git -C ... show --stat HEAD` (one signed-off commit per `yes`, only `hass/content` and generated site files).
- `git -C ~/.local/share/hass/writer status --porcelain` empty; `python3 hass/sitegen.py --check` and `python3 hass/migration_check.py` run in the writer exit 0.
- `python3 hass/editor.py history` lists the changes; `python3 hass/health.py` clean; `~/.config/hass/STOP` still there; the live site and its release journal untouched (no `release`/publish entries; `git -C <live deploy checkout> status` unchanged).
- Every reply read by a person against `docs/hass/VOICE.md`; correspondence log has no `voice-fallback` entries for the test.

**Revert (operator):**
1. In `host.json` set `"approvals"` back to `"hold"`; `systemctl --user restart hass-worker`.
2. `python3 hass/editor.py recover` (settles any journal; never re-applies).
3. On the writer worktree only (branch `hass/live`, never `main`): `git -C ~/.local/share/hass/writer reset --hard BASE`. Check `git status` empty and `sitegen --check` ok.
4. If the state folder should look as if nothing happened: restore the step 4 backup into a new directory with `statebackup.py restore ... --paused` and swap it in (attended); otherwise leave the drafts as history.
5. Remove `~/.config/hass/STOP` only when G says publishing may resume.

## Defects as follow-up cards (name: one-line spec)

1. **HASS-FIX-SPECIALS-DEAL-KIND**: add `"deal"` to `STRING_KINDS` in `hass/interpret_check.py` and add a test that every arg kind in the op registry passes `_kind_ok`.
2. **HASS-FIX-SPECIALS-IN-PROMPT**: list current specials (id, title, last day) in the interpreter prompt like hikes, so "take the X special off" can find one.
3. **HASS-FIX-SPECIALS-DRAFT-TEXT**: show a special's title, deal line and last day in the draft and the saved/undo texts instead of "a detail ... more than I can show here"; stop the interpreter inventing a `product` link.
4. **HASS-FIX-UNDO-KEY-ORDER-AND-ADD**: make undo restore the original record bytes and make undo of an add remove the record (hike, maker, product and its picture), not hide/cancel it.
5. **HASS-FIX-EDITOR-ERROR-RECOVER-NOW**: when `editor.apply` raises, recover at once (restore the file, drop the journal), mark the draft failed, reply "I couldn't save that, nothing changed", and make `status` list an `approved` draft instead of "Everything is ready".
6. **HASS-FIX-STALE-AFTER-CRASH**: a draft prepared while a half-written file is on disk is later called "the website changed"; prepare against HEAD, and never leave an `approved` draft unanswered.
7. **HASS-FIX-ISO-DATE-IN-DRAFT**: stock drafts show "2026-11-08"; word the date and make the in-service voice check replace it.
8. **HASS-FIX-RAN-OUT-MEANS-HIDE**: "take X off the site, we ran out for the season" should ask hide or sold out, not start the shelf check.
9. **HASS-FIX-DRAFT-WAITING-REPLY-TRUTH**: "It already says that: X is hidden" while only a draft for X waits is untrue; say a change is waiting and give its code.
10. **HASS-WIRE-PHOTOS-IN-HOST**: give `Conversation(photos=...)` a source in `host.py` (the real worker refuses all photos today).
11. **HASS-FIX-NEWITEM-PHOTO-CARRY**: a message after a photo that names a new product should become `product.add` with that photo (today: "Send the photo with the product name as its caption", "That doesn't look quite right", or a repeated maker question); also stop the draft listing the name twice.
12. **HASS-DECIDE-LIVE-POLICY-IN-PRIVATE**: decide whether the live-policy check (origin/organic, health, award, phone, email, trail facts) should also run in private mode; today an organic claim is drafted and applied.
13. **HASS-FIX-MAKER-PLACE-STORY-WARNING**: after a maker's place changes, warn when the maker's story text still names the old place.
14. **HASS-FIX-PREVIEW-FAIL-POLICY**: a failed result preview leaves the change committed; decide keep or revert, and drop the "copying it to the website" wording from private-mode `status`.
15. **HASS-FIX-PREVIEW-SHOWS-CHANGE**: maker, hike and stock phone pictures show the wrong part of the page; scroll to or crop the changed record.
16. **HASS-FIX-CLAIM-QUESTION-FIELDNAMES**: the claim question shows raw field names ("brand" and "displayBrand"); word them, and make the in-service check replace a reply that breaks the voice rule.

## Limits

- The scratch runs at main 0a8114c; PR #532 (stock) merged after that and was not in the runtime under test, although the sold-out flow ran. A newer main may differ.
- The interpreter is a model; the same message can give a different answer on another run (the photo cases varied between attempts). Scenario counts are one run each.
- Fixture interpreters supplied the ops for the injections, the specials remove and the product-with-photo apply; those prove the apply path, not the interpretation.
- "Build fails after the edit" (b) patches the post-check for one call; (a) is a real git failure. Preview failure is a patched `Previewer.capture`.
- Nothing here proves the live host: Mac, forwarder, live writer and live timings were not exercised.
