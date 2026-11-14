# What Hass can do

Generated from the skill registry. Do not edit this page or capabilities.json by hand.

This describes the code in this version, not what is installed on the phone or enabled by host settings.
Every change still needs its existing approval and policy checks. A private test is not live permission.
Front end, site, till and reports are the four packs; General help has no changing target.
A0 means no owner yes; A1 means owner yes. A2 (second yes) and A3 (named exception) are not enabled.
Sandbox support describes the existing private writer/preview, not AVB-11's future per-target switch.
The per-target switch, audit writer and pack executors are separate work; log fields below declare names only.

Rebuild: `python3 hass/capabilities.py`. Check: `python3 hass/capabilities.py --check`.

## Website

| Skill | What it does | Gate, private test and status | Changing targets | Declared log fields |
|---|---|---|---|---|
| add a hike (hike.add) | Put a new hike on the hike page: day, time and where to meet. Sign-up stays off unless you say so. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| cancel a hike (hike.cancel) | Cancel a scheduled hike, with an optional one-line note on the page. Nobody is told. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| change a hike (hike.edit) | Change a scheduled hike: its name, where to meet, how hard, what to bring, or sign-up. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| write down how a hike went (hike.recap) | Mark a hike that has happened as done and keep your words on how it went. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| run a hike again (hike.repeat) | Copy a hike onto a new day and time: its name, text, route and sign-up setting. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| move a hike to another day or time (hike.reschedule) | Move a scheduled hike to a new day or time. Guests who signed up are not told. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| add a new product (item.add) | Add a new product from a photo and a few words: its maker if new, the picture, and whether it is in stock. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| change a product (item.edit) | Change a product's name, description, maker or shelf. Prices are not kept on the website. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| hide a product (item.hide) | Take one or more products off the website. Nothing is deleted; they can come back. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| change a product's picture (item.picture) | Put the photo he sent on one product, with a caption that says what it shows. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| bring a hidden product back (item.restore) | Put one or more hidden products back on the website. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| add a maker (maker.add) | Add a maker with their town and a short about text; with no story, one line says where they are based. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change a maker or their about text (maker.edit) | Change a maker's name, town, about text or website link; a new story replaces the whole text. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| stop carrying a maker (maker.hide) | Hide a maker, and with your yes their products too; nothing is deleted. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| bring a maker back (maker.restore) | Bring a hidden maker back; their products come back one by one when you ask. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change the store story (page.about) | Change the “Come on in” story on the home page. For the separate About template use front.page. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change the home page headline or intro (page.home) | Change the two-line headline or the intro on the home page, or put the shop's own words back. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change the home page photo (page.photo) | Use the photo he sent as the home page photo, or put the shop's own photo back. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change the phone number or the address (shop.contact) | Change or remove the store phone number, or change the street address and town. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change the store hours (shop.hours) | Change the opening hours. Days he did not name keep exactly what the site says now. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| put up a notice on the home page (shop.notice) | Put up, replace or take down the one dated notice at the top of the home page. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| put something on special (specials.add) | Put an item or a deal in this week's specials box on the home page, shown until a last day. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| clear the finished specials (specials.clear_expired) | Tidy the saved list by dropping specials whose last day has passed. They no longer show on the page. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change a special (specials.edit) | Change one special: its title, deal line, product, first day or last day (for example extend it). | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| take a special off (specials.remove) | Take one special off the home page before its last day. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| show this week's specials (specials.show) | Say which specials are on now and which are coming up, with each deal as it was typed. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| record the shelf check (stock.checked) | Record that the shelves were checked today (or a day this week), with what was found. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| stop showing a word on a product (stock.clear) | Take the in stock, low or sold out label off a product's card. Never sets sold out. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |
| record when more is coming (stock.restock) | Note the day more of one product is expected. A day only; never a count, never the shelf word. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| change what's in stock (stock.set) | Mark one or more products in stock, low, or sold out after today's shelf check. | A1: your yes first; private test supported; eligible for live approval; registered; owners | site | subjects, fields |

## Front end

| Skill | What it does | Gate, private test and status | Changing targets | Declared log fields |
|---|---|---|---|---|
| put a dated banner across the top (front.banner) | Schedule one short line across the top of home and hike, with an optional own-site link. | A1: your yes first; private preview only; private only; registered; owners | site | fields |
| add, edit or remove a question and answer (front.faq) | Add or edit a question and answer on Questions, or remove a question; the first entry shows the page. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| fill or hide a fixed template page (front.page) | Fill or hide About, Getting here, Our policies or Questions using the owner's words and a fixed template. | A1: your yes first; private preview only; private only; registered; owners | site | subjects, fields |
| move or hide a home page part (front.sections) | Reorder the four home parts, hide why we do it or newsletter, or put the original order back. | A1: your yes first; private preview only; private only; registered; owners | site | fields |
| add a questions page (page.faq) | The site has no FAQ page and a new page is a design change: say so and write it down. | A0: no yes needed; no target changes; writes the request down, not the change; retired; owners | none | none |

## Till

Nothing registered yet.

## Reports

| Skill | What it does | Gate, private test and status | Changing targets | Declared log fields |
|---|---|---|---|---|
| morning shelf report (report.shelf) | Say what is sold out or running low from the last shelf check, and any hikes. Not stock counts; sends nothing. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| write a post caption for a hike (social.hike) | Write an announcement caption for one upcoming hike, to copy. Nothing is posted or sent. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| write a post caption for a product (social.item) | Write an Instagram caption for one product on the website, to copy. Nothing is posted. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| write a post caption for a maker (social.maker) | Write a meet-the-maker caption for one maker with a story, to copy. Nothing is posted. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| write a post caption from a hike recap (social.recap) | Write a caption from the owner's saved recap of a hike that happened, to copy. Nothing is posted. | A0: no yes needed; no target changes; read only; registered; owners | none | none |

## General help

| Skill | What it does | Gate, private test and status | Changing targets | Declared log fields |
|---|---|---|---|---|
| answer a site question (answer.site) | Answer hours, products, makers and hikes from saved site content; confirmed sign-ups only, never prices or sales. | A0: no yes needed; no target changes; read only; registered; owners | none | none |
| write it down for later (backlog.log) | Nothing fits: write the request down, say I can't do that yet, change nothing. | A0: no yes needed; no target changes; writes the request down, not the change; registered; owners | none | none |
