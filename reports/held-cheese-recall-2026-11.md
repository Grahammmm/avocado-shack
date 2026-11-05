Both products remain held. This report does not authorize release or confirm that any package is safe.

# Held cheeses: official recall evidence (November 2026)

- Research date (accessed): 2026-11-04.
- Repository checkout: avocado-shack `main` at `a69c3e0fe8ff9fa9b3b5acaf2c15dfd48bdf497f`.
- Products compared: `photo-product-040` "Raw milk white cheddar" (brand Sierra Nevada) and `photo-product-133` "Raw Milk Goat Cheddar" (brand Sierra Nevada). Both are `status: held` in `hass/content/products.json`; this report changes neither record nor `storefront-mockup/held-products.json`.
- Method: public official web pages were read as text only (no downloads, no contact with the maker, a regulator or the owner). Pages were fetched through a text extractor and a web search; this is not a claim of exhaustive historical coverage.

## What was searched

| Source | Query or page | Result |
|---|---|---|
| FDA recalls | Search "Sierra Nevada Cheese Graziers raw milk recall"; page below | One company announcement found (notice 1) |
| FDA outbreak advisory | Linked from notice 1; page below | One advisory found (notice 2) |
| CDPH food recalls list | `https://www.cdph.ca.gov/Programs/CEH/DFDCS/Pages/FDBPrograms/FoodSafetyProgram/FoodRecalls.aspx` (page last updated 2026-11-04) | One entry found, Sierra Nevada Cheese Company, 09/25/26, marked UPDATED (notice 3) |
| Maker, `https://sierranevadacheese.com/` | Homepage text read; guessed paths `/pages/recall`, `/pages/graziers-recall`, `/pages/graziers-raw-milk-cheese-recall`, `/pages/product-recall` | **No item-specific recall page found.** The homepage text returned by the extractor contained no recall notice. The guessed paths were not found (404 or not found). The maker's own wording is known only second-hand: FDA notice 1 says the company issued notices through its website and social media. The hold reason in the repository says the site displayed the recall earlier; that was not reproduced today. |
| CDC | `https://cdc.gov/ecoli/outbreaks/raw-milk-cheese-09-26` (search result text) | Names the same event. Not an FDA/CDPH/maker notice, so not listed as a notice; shown for context only. |

## Notices

All three notices describe one event: Sierra Nevada Cheese Company's recall of all Graziers raw milk cheese for possible E. coli O26:H11. FDA's and CDPH's pages republish or summarise the company's announcement and the FDA advisory, so they are not independent verification of each other.

### Notice 1: FDA company announcement

| Field | Value |
|---|---|
| Issuing body | FDA (posting the company's announcement; FDA does not endorse the product or company) |
| Title | "Sierra Nevada Cheese Company Recalls Graziers Raw Milk Cheese Because of Possible Health Risk" |
| Dates | Company announcement date 2026-09-28; FDA publish date 2026-09-29; content current as of 2026-09-29; accessed 2026-11-04. No later update or correction seen on the page. |
| Brand / product | Brand "Sierra Nevada Graziers"; "Monterey Jack, Jalapeno Jack, Medium Cheddar, and Sharp Cheddar raw milk cheeses". Milk species: not stated in this notice. |
| Sizes and codes | 8oz Square: Monterey Jack (UPC 6-87652-16400-9), Jalapeño Jack (UPC 6-87652-16403-0), Medium Cheddar (UPC 6-87652-16506-8), Sharp Cheddar (UPC 6-87652-16507-5). 16 oz Brick: Medium Cheddar (UPC 6-87652-16501-3). 5lb Loaf: Monterey Jack (Item 6425), Jalapeño Jack (Item 6426), Medium Cheddar (Item 6510), Sharp Cheddar (Item 6511). 40lb Block: "Graziers Raw Milk Cheddar block" (Item 6515; 6516). |
| Lot / best-by | not stated in this notice. Quote: "the investigation has not been narrowed to a specific lot, date code, or production date." |
| Scope quote | "recalling all the Graziers Raw Milk Cheese products listed below currently in distribution." |
| Illness link | "illnesses have been epidemiologically associated with consumption of Graziers Raw Milk Medium Cheddar" (13 illnesses). |
| URL | https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/sierra-nevada-cheese-company-recalls-graziers-raw-milk-cheese-because-possible-health-risk |

### Notice 2: FDA outbreak advisory

| Field | Value |
|---|---|
| Issuing body | FDA (with CDC) |
| Title | "Outbreak Investigation of E. coli O26:H11: Raw Milk Cheese (September 2026)" |
| Dates | Page shows "Current Update" 2026-09-25; accessed 2026-11-04. The advisory says the firm was contacted and a recall initiated on 2026-09-24. Note the company announcement in notice 1 is dated 2026-09-28; the dates differ and were not reconciled. |
| Brand / product | "Sierra Nevada Graziers grass-fed raw milk cheeses: medium cheddar, sharp cheddar, jalapeno jack, and Monterey jack". Milk species: not stated. |
| Sizes and codes | "8-oz or 16-oz packages" at retail and "5-lb loaves" for food service or wholesale. UPC and item numbers: not stated in this notice (see notice 1). |
| Lot / best-by | not stated in this notice. |
| Scope quote | Firm "agreed to and initiated a recall of all Graziers Raw Milk Cheeses." Also: "If you refrigerated or froze cheese without the original packaging and can't tell if it's part of the recall, throw it away." |
| URL | https://www.fda.gov/food/outbreaks-foodborne-illness/outbreak-investigation-e-coli-o26h11-raw-milk-cheese-september-2026 |

### Notice 3: CDPH food recall information sheet

| Field | Value |
|---|---|
| Issuing body | California Department of Public Health, Food and Drug Branch (posting the firm's announcement) |
| Title | "Sierra Nevada Cheese Company – All Graziers Grass-fed Raw Milk Cheeses (UPDATED) 09/25/26"; sheet heading "Sierra Nevada Cheese Company Recalls All Graziers Grass-fed Raw Milk Cheeses Due to Potential E.coli Contamination" |
| Dates | Recall date 09/25/26 (as printed); marked UPDATED; accessed 2026-11-04. The sheet shows no separate update date. |
| Brand / product | "Sierra Nevada Graziers grass-fed raw milk cheeses: medium cheddar, sharp cheddar, jalapeno jack, and Monterey jack". Milk species: not stated. |
| Sizes and codes | not stated in this notice (it refers to FDA and a "Retail Distribution List" that was not read). Lot / best-by: not stated in this notice. Recall class: N/A. |
| URL | https://www.cdph.ca.gov/Programs/CEH/DFDCS/CDPH%20Document%20Library/FDB/FoodSafetyProgram/FoodRecalls/September2026/fdbFrSNCC2n.pdf |

### Maker's own page

No item-specific notice URL was found (see search table). Nothing is claimed from the maker's page. Michael can check https://sierranevadacheese.com/ himself for a current recall banner or notice.

## Comparison with the two held products

This classifies only whether a notice names the product, not whether a particular package is in a recalled lot. Every notice says the recall is of all products listed, with no lot or date limit stated, so a package of a listed product would not be cleared by its lot code either.

### photo-product-040 "Raw milk white cheddar" (brand Sierra Nevada): cannot tell

- Notices: 1, 2, 3 (links above).
- Reason: the catalog record says "variety to confirm" and gives no Graziers line, milk species or size (the "8 oz package" in the repository is a sample unit, not a verified package). The notices name Graziers Medium Cheddar, Sharp Cheddar and a "Cheddar block", but none says "white cheddar", and none says whether it covers every Sierra Nevada raw cheddar. A match needs the notice's explicit brand and product, and this candidate does not state either.
- Michael must read on the package: printed brand (is "Graziers" on it?); full cheese name (medium, sharp, white, other); milk species; "raw" or "pasteurized" wording; net weight (8 oz, 16 oz, other); UPC (compare with the UPCs in notice 1); lot or batch code; best-by or use-by date. If the package shows Graziers Raw Milk Medium or Sharp Cheddar at 8 oz or 16 oz with a UPC listed in notice 1, it is a product the notice names.
- Unknown from the repository: all of the above.

### photo-product-133 "Raw Milk Goat Cheddar" (brand Sierra Nevada): cannot tell

- Notices: 1, 2, 3 (links above).
- Reason: no notice names a goat-milk product or a goat cheddar, and none states a milk species. That does not make this a "no match": the notices do not say they exclude other Sierra Nevada raw cheeses, and the record gives no Graziers line or exact variant. The catalog name and the one photograph (`IMG_9722.jpg`) were not re-reviewed, and the product image is AI artwork, which is not packaging evidence.
- Michael must read on the package: printed brand and any "Graziers" line; full cheese name; milk species (goat or cow); "raw" or "pasteurized" wording; net weight; UPC; lot or batch code; best-by or use-by date.
- Unknown from the repository: all of the above; `sampleUnit` "one package" says nothing about size.

## Edge cases applied

- `missing_lot_or_size`: no notice gives a lot or best-by code, and notices 2 and 3 give no sizes or UPCs. Written as "not stated in this notice"; no sample unit or other notice's code was borrowed.
- `generic_white_cheddar_or_goat_variant`: neither catalog variety is named exactly, so each stays "cannot tell". No whole-brand recall is assumed.
- `no_result_or_blocked_official_page`: the maker's recall page was not found. The comparison stays "cannot tell"; this is not a finding that the products were not recalled.
- `updated_or_conflicting_notice`: CDPH is marked UPDATED, and the FDA advisory (2026-09-25) and company announcement (2026-09-28) carry different dates. No scope conflict between the notices was seen. The update content was not available beyond what is quoted.
- `positive_or_negative_identity`: neither a match nor a no match would change either hold or permit sale.

## Not done

No physical inspection, original-photo review, contact with Michael, the maker or a regulator, or safety determination. The CDPH "Retail Distribution List" and the FDA product photos were not read.

Identity comparison: neither candidate can be placed against a notice from the repository alone. Lot applicability: no notice limits the recall by lot, so lot codes cannot narrow it. Unchanged hold: both products stay held.

Both photo-product-040 and photo-product-133 remain held. Michael must compare the actual package with the linked official notice; any release is the owner's decision.
