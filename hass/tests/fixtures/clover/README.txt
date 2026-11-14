The fixtures in this folder are written by hand from the shapes in Clover's public developer documentation
(docs.clover.com, retrieved 2026-11-09; see docs/hass/CLOVER.md for the page list). They are not recordings of a real merchant:

* ids are obviously fake (`FAKEITEM00001`, `FAKECAT000001`) and the merchant id used by the tests is `FAKEMERCH0001`;
* names and prices are made up; `cost` is present on purpose, to prove the mapper drops it;
* no token, header, customer, order, payment or employee data exists here, and a test fails if a UUID-shaped or token-shaped string appears.

HASS-CLOVER-2 adds `merchant.json` (the merchant's basic record, as GET /v3/merchants/{mId} answers it, with no owner or address link) and
`item_stocks.json` (one page of GET /v3/merchants/{mId}/item_stocks; item 1's count differs from its expanded itemStock on purpose, to
prove the sync takes the count from the item_stocks endpoint).
