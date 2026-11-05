# Product description claims — recorded sources (AV1104-11)

- Report date: 2026-11-05
- Audited main SHA: `72dbe74448537346c4fcc81768ec034267177ca8` (full)
- Canonical inputs: `hass/content/products.json` (active records only); recorded-source families: `storefront-mockup/producer-research-log.json`, `hass/content/makers.json` (maker key and place), `storefront-mockup/new-products.json` and `storefront-mockup/completion-new-products.json` (matching stable ids).
- Selection rule: every sentence of an active product description that asserts a product-specific checkable fact: a maker, farm or town; a family operation; raw, cultured or aged state; manufacture or process; an ingredient or composition; organic status in prose; or alcohol/caffeine absence. Taste, texture, metaphor, cooking and serving suggestions are excluded unless they also assert such a fact (“Eat one raw” is advice; “Raw and unfiltered” is a claim). A sentence that mixes advice with a statement of what the product is, its state or its ingredients is included, and only its factual clauses are assessed (“Dried mushrooms are a pantry shortcut…” states the dried state; “Blueberry preserves for buttered toast…” states the product type and fruit); a bare restatement of the product name inside pure advice, or a quality word such as “fresh”, is not. Every excluded description was re-read against this rule in the fix round for the review RETURN. A place inside a blend name is not treated as production origin.
- Order rule: the nine shelves in the site’s filter-button order (Fruit, Vegetables, Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread, Flowers, from `storefront-mockup/index.html` L23); within a shelf, the canonical active-record order of `products.json`, never alphabetical. A product sits on the shelf of its `category`, so some products sit on a shelf their name does not suggest (for example tortilla chips and cantaloupe are on Vegetables, Gouda is on Dairy).
- **Limitation: Recorded support is not independent or current verification; the owner decides any change.** This report certifies nothing as true, shows no present stock, and edits no record.
- Verdict words: **recorded support** = the repo records state the clause; **partial support** = a record supports part of it or only the maker, not this product; **no source found** = nothing in the four source families states it. A maker story in `makers.json` is shown only as “secondary context” and is never counted as independent support. A brand, a producerKey, a search-query title, a photo file name or a generic maker range does not prove a specific ingredient, process or origin. Research-log quotes are short fragments; contact details and full search results are left out.
- Out of scope: the automatic Organic badge rule is the separate audit AV1052-14, and the fixed page, template and maker-story copy is the separate audit AV0007-08. Description sentences that themselves say “organic” stay here. Held products are not audited (listed below).

## Reconciled counts

- Active products reviewed: 170 (all; “about 49” in the card is a discovery estimate, not a target)
- Active products with at least one qualifying sentence: 88
- Qualifying sentences: 89
- Checkable clauses assessed: 155
- Unsupported clauses (verdict starts “no source found”): 93
- Clauses with recorded support: 32; partial support: 30

| Shelf | Active products | With qualifying sentence | Qualifying sentences |
|---|---|---|---|
| Fruit | 13 | 0 | 0 |
| Vegetables | 52 | 1 | 1 |
| Dairy & cheese | 20 | 18 | 18 |
| Eggs | 1 | 0 | 0 |
| Meat | 3 | 3 | 3 |
| Pantry | 61 | 47 | 48 |
| Drinks & coffee | 15 | 15 | 15 |
| Bread | 4 | 4 | 4 |
| Flowers | 1 | 0 | 0 |

Held/inactive records, excluded and not audited (not released by this report): photo-product-040 Raw milk white cheddar (status held); photo-product-133 Raw Milk Goat Cheddar (status held).

## Claims by shelf

### Fruit (13 active products)

No description on this shelf contains a qualifying checkable-fact sentence (reasons in the coverage appendix).

### Vegetables (52 active products)

#### photo-product-018 — Montaña de Oro Sea Salt tortilla chips

- Shelf: Vegetables. Locator: `hass/content/products.json` L153 (`id` photo-product-018, field `description`). Maker key: “Taco Works”.
- **S1** “Taco Works chips with Montaña de Oro sea salt, made in San Luis Obispo.”
  - Clause: Taco Works is a tortilla-chip maker — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L28 (query “Taco Works official history”, result record #6): “Taco Works, Inc., a wholesale tortilla chip manufacturer in San Luis Obispo, California”
    - Note: Maker-level extract; does not name this bag.
  - Clause: Montaña de Oro line with salt — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L28 (query “Taco Works official history”, result record #6): “Montana De Oro Tortilla Chips... a white corn tortilla chip with salt”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L109, maker "Taco Works": “The Montaña de Oro line keeps things straightforward: white corn and salt.”
    - Note: Supports a Montana De Oro chip with salt. “sea salt” is not stated: no source found for “sea”.
  - Clause: made in San Luis Obispo — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L28 (query “Taco Works official history”, result record #6): “a wholesale tortilla chip manufacturer in San Luis Obispo, California”
    - maker-location record: `hass/content/makers.json` L108, maker "Taco Works", place "San Luis Obispo, California"
    - Note: Maker-level.

### Dairy & cheese (20 active products)

#### photo-product-025 — Straus half-and-half

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L736 (`id` photo-product-025, field `description`). Maker key: “Straus”.
- **S1** “Enough cream to give the coffee some body.”
  - Clause: cream product (half-and-half) made by Straus — **partial support**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L37, maker "Straus": “The creamery carries that commitment into its milk, cream and cultured products.”
    - Note: Secondary context only; no Straus query exists in the research log, and the story does not name half-and-half.

#### photo-product-026 — Straus heavy whipping cream

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L747 (`id` photo-product-026, field `description`). Maker key: “Straus”.
- **S1** “For a sauce that needs richness or a dessert that needs nothing more than a spoonful of cream.”
  - Clause: cream (heavy whipping) made by Straus — **partial support**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L37, maker "Straus": “The creamery carries that commitment into its milk, cream and cultured products.”
    - Note: Secondary context only; no Straus query exists in the research log.

#### photo-product-027 — Organic whole milk

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L758 (`id` photo-product-027, field `description`). Maker key: “Straus”.
- **S2** “Straus brings its organic dairy tradition to an everyday staple.”
  - Clause: Straus has an organic dairy tradition — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L37, maker "Straus": “its family farm became certified organic in 1994”
    - Note: No Straus query exists in the research log. Organic status of this milk is also the subject of AV1052-14.

#### photo-product-029 — Ragged Point cheese

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L780 (`id` photo-product-029, field `description`). Maker key: “Stepladder”.
- **S1** “Ragged Point cheese from Stepladder’s Cambria creamery.”
  - Clause: made by Stepladder — **no source found (brand/producerKey link only)**
    - Note: No Stepladder query exists in the research log; the producerKey connects the record to the maker but does not prove this cheese.
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
    - Note: Location of the maker, not of this cheese.
  - Clause: "creamery" (a cheese-making premises) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “Stepladder makes its cheeses in a restored barn in the hills of Cambria”
    - Note: The story says barn, not creamery.

#### photo-product-030 — Stepladder cultured butter

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L791 (`id` photo-product-030, field `description`). Maker key: “Stepladder”.
- **S1** “Cultured butter from the Cambria creamery, best given something simple to work with.”
  - Clause: cultured butter (process) — **no source found**
    - Note: Cambria place cannot certify the cultured process; the Stepladder story mentions only cheeses. The log hit for “Cultured Butter” belongs to Sierra Nevada, a different maker.
  - Clause: from the Cambria creamery (Stepladder) — **no source found (brand/producerKey link only)**
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
  - Clause: "creamery" — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “Stepladder makes its cheeses in a restored barn in the hills of Cambria”

#### photo-product-033 — Stepladder Rocky Butte cheese

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L802 (`id` photo-product-033, field `description`). Maker key: “Stepladder”.
- **S1** “Rocky Butte cheese from Stepladder’s Cambria creamery.”
  - Clause: made by Stepladder — **no source found (brand/producerKey link only)**
    - Note: No Stepladder query exists in the research log; the producerKey connects the record to the maker but does not prove this cheese.
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
    - Note: Location of the maker, not of this cheese.
  - Clause: "creamery" (a cheese-making premises) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “Stepladder makes its cheeses in a restored barn in the hills of Cambria”
    - Note: The story says barn, not creamery.

#### photo-product-034 — Stepladder Bixby cheese

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L813 (`id` photo-product-034, field `description`). Maker key: “Stepladder”.
- **S1** “Bixby cheese from Stepladder’s Cambria creamery.”
  - Clause: made by Stepladder — **no source found (brand/producerKey link only)**
    - Note: No Stepladder query exists in the research log; the producerKey connects the record to the maker but does not prove this cheese.
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
    - Note: Location of the maker, not of this cheese.
  - Clause: "creamery" (a cheese-making premises) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “Stepladder makes its cheeses in a restored barn in the hills of Cambria”
    - Note: The story says barn, not creamery.

#### photo-product-035 — Chèvre

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L824 (`id` photo-product-035, field `description`). Maker key: “Stepladder”.
- **S1** “Fresh goat cheese from Stepladder in Cambria.”
  - Clause: goat cheese made by Stepladder — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “with LaMancha goats grazing on the property”
    - Note: Goats on the property do not show that this cheese is a goat-milk product of Stepladder.
  - Clause: fresh (unaged) style — **no source found**
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"

#### photo-product-037 — Cal Poly chipotle cheddar

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L835 (`id` photo-product-037, field `description`). Maker key: “Cal Poly”.
- **S1** “Chipotle cheddar from Cal Poly’s creamery.”
  - Clause: made at Cal Poly’s creamery — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
  - Clause: cheddar style / named variety (chipotle) — **no source found**

#### photo-product-038 — Cal Poly white cheddar

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L846 (`id` photo-product-038, field `description`). Maker key: “Cal Poly”.
- **S1** “White cheddar from Cal Poly’s creamery.”
  - Clause: made at Cal Poly’s creamery — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
  - Clause: cheddar style / named variety (white) — **no source found**

#### photo-product-039 — Cal Poly Highland cheddar

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L857 (`id` photo-product-039, field `description`). Maker key: “Cal Poly”.
- **S1** “Highland cheddar from Cal Poly’s creamery.”
  - Clause: made at Cal Poly’s creamery — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
  - Clause: cheddar style / named variety (highland) — **no source found**

#### photo-product-125 — Whole Milk Plain European Style yogurt

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L868 (`id` photo-product-125, field `description`). Maker key: “Straus”.
- **S1** “Plain yogurt is not unfinished yogurt.”
  - Clause: plain (unflavoured) yogurt (composition) — **no source found**
    - Note: Name and sentence only; no record states the composition.
  - Clause: yogurt made by Straus — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L37, maker "Straus": “The creamery carries that commitment into its milk, cream and cultured products.”
    - Note: Maker-wide mention of cultured products; it does not say yogurt.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L383: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9719.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-127 — Sour cream

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L890 (`id` photo-product-127, field `description`). Maker key: “Straus”.
- **S1** “A cool, cultured counterpoint to heat.”
  - Clause: cultured (process) — **no source found**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L37, maker "Straus": “The creamery carries that commitment into its milk, cream and cultured products.”
    - Note: Maker-wide mention of cultured products; it does not say sour cream.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L421: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9719.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-128 — Big Sur cheese

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L901 (`id` photo-product-128, field `description`). Maker key: “Stepladder”.
- **S1** “Big Sur cheese from Stepladder’s Cambria creamery.”
  - Clause: made by Stepladder — **no source found (brand/producerKey link only)**
    - Note: No Stepladder query exists in the research log; the producerKey connects the record to the maker but does not prove this cheese.
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
    - Note: Location of the maker, not of this cheese.
  - Clause: "creamery" (a cheese-making premises) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L13, maker "Stepladder": “Stepladder makes its cheeses in a restored barn in the hills of Cambria”
    - Note: The story says barn, not creamery.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L440: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9720.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-129 — Marinated Fromage Blanc

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L912 (`id` photo-product-129, field `description`). Maker key: “Stepladder”.
- **S1** “Marinated fromage blanc from Stepladder.”
  - Clause: marinated fromage blanc (product identity and marinade) — **no source found**
    - Note: The October note records only a photographed product; it states no ingredient or process, and its notes say “Selling units, price and availability remain development assumptions.”
  - Clause: from Stepladder — **no source found (brand/producerKey link only)**
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L459: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9720.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-130 — Gouda

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L923 (`id` photo-product-130, field `description`). Maker key: “Cal Poly”.
- **S1** “Gouda from Cal Poly’s creamery in San Luis Obispo.”
  - Clause: made at Cal Poly’s creamery — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
  - Clause: San Luis Obispo location — **recorded support**
    - maker-location record: `hass/content/makers.json` L42, maker "Cal Poly", place "San Luis Obispo, California"
  - Clause: Gouda style — **no source found**
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L478: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9722.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-131 — Hatch Chile Sierra Jack

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L934 (`id` photo-product-131, field `description`). Maker key: “Sierra Nevada”.
- **S1** “Hatch chile Sierra Jack pairs cheese with chile.”
  - Clause: Hatch chile Jack is a Sierra Nevada Cheese line — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L36 (query “Sierra Nevada cheese official about”, result record #8): “Habanero Jack, Hatch<br>Chile Jack”
    - Note: A directory listing names the line for the maker; it does not state the chile as an ingredient of this product or tie it to this package.
  - Clause: contains chile (ingredient) — **no source found**
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L497: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9722.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-132 — Habanero Sierra Jack

- Shelf: Dairy & cheese. Locator: `hass/content/products.json` L945 (`id` photo-product-132, field `description`). Maker key: “Sierra Nevada”.
- **S1** “Habanero Sierra Jack puts heat into the cheese drawer.”
  - Clause: Habanero Jack is a Sierra Nevada Cheese line — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L36 (query “Sierra Nevada cheese official about”, result record #8): “Habanero Jack, Hatch<br>Chile Jack”
    - Note: Same limit as above.
  - Clause: contains habanero (ingredient) — **no source found**
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L516: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9722.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

### Eggs (1 active products)

No description on this shelf contains a qualifying checkable-fact sentence (reasons in the coverage appendix).

### Meat (3 active products)

#### photo-product-021 — Alle-Pia Calabrese salamini

- Shelf: Meat. Locator: `hass/content/products.json` L1671 (`id` photo-product-021, field `description`). Maker key: “Alle-Pia”.
- **S1** “Calabrese salamini from Alle-Pia on the Central Coast.”
  - Clause: made by Alle-Pia on the Central Coast — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L8 (query “Alle Pia salumi official about”, result record #1): “Alle-Pia Salami is made on the Central Coast of California”
    - maker-location record: `hass/content/makers.json` L48, maker "Alle-Pia", place "California’s Central Coast"
    - Note: Maker-level.
  - Clause: Calabrese salami — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L8 (query “Alle Pia salumi official about”, result record #1): “Barolo, Tartufo, Calabrese, Finocchiona, Cacciatorino & Sopressa Salami”
    - Note: “salamini” (the small format) is not stated: no source found.

#### photo-product-022 — Alle-Pia guanciale

- Shelf: Meat. Locator: `hass/content/products.json` L1682 (`id` photo-product-022, field `description`). Maker key: “Alle-Pia”.
- **S1** “Guanciale is a reason to put a pan on the stove.”
  - Clause: guanciale (cured pork cheek) made by Alle-Pia — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L8 (query “Alle Pia salumi official about”, result record #1): “Alle-Pia Fine Cured Meats”
    - checked absence: `storefront-mockup/producer-research-log.json` L8 (query “Alle Pia salumi official about”) does not contain “guanciale”
    - Note: Maker-level: Alle-Pia is recorded as a cured-meat maker; guanciale is not named.

#### photo-product-023 — Alle-Pia mortadella

- Shelf: Meat. Locator: `hass/content/products.json` L1693 (`id` photo-product-023, field `description`). Maker key: “Alle-Pia”.
- **S1** “Mortadella from Alle-Pia.”
  - Clause: Alle-Pia makes mortadella — **no source found**
    - Note: The Alle-Pia result lists salami (Barolo, Tartufo, Calabrese and others) and an ’Nduja spread. Its only “Mortadella” hit is a Greek restaurant menu (casagiacomo.gr) inside the same search result, which is not Alle-Pia.

### Pantry (61 active products)

#### photo-product-002 — Linn's triple berry preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1000 (`id` photo-product-002, field `description`). Maker key: “Linn's”.
- **S1** “Triple berry preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: triple berry (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: triple berry as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.

#### photo-product-003 — Linn's blueberry preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1011 (`id` photo-product-003, field `description`). Maker key: “Linn's”.
- **S1** “Blueberry preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: blueberry (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: blueberry as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.

#### photo-product-004 — Linn's boysenberry preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1022 (`id` photo-product-004, field `description`). Maker key: “Linn's”.
- **S1** “Boysenberry preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: boysenberry (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: boysenberry as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.

#### photo-product-005 — Linn's orange marmalade

- Shelf: Pantry. Locator: `hass/content/products.json` L1033 (`id` photo-product-005, field `description`). Maker key: “Linn's”.
- **S1** “Orange marmalade for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: orange (marmalade) (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: orange (marmalade) as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.

#### photo-product-008 — Cal Poly strawberry jam

- Shelf: Pantry. Locator: `hass/content/products.json` L1044 (`id` photo-product-008, field `description`). Maker key: “Cal Poly”.
- **S1** “Strawberry jam, from Cal Poly’s food program in San Luis Obispo.”
  - Clause: made by Cal Poly’s food program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
  - Clause: San Luis Obispo location — **recorded support**
    - maker-location record: `hass/content/makers.json` L42, maker "Cal Poly", place "San Luis Obispo, California"

#### photo-product-009 — Cal Poly raspberry jam

- Shelf: Pantry. Locator: `hass/content/products.json` L1055 (`id` photo-product-009, field `description`). Maker key: “Cal Poly”.
- **S1** “Raspberry jam, from Cal Poly’s food program in San Luis Obispo.”
  - Clause: made by Cal Poly’s food program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
  - Clause: San Luis Obispo location — **recorded support**
    - maker-location record: `hass/content/makers.json` L42, maker "Cal Poly", place "San Luis Obispo, California"

#### photo-product-010 — Cal Poly blackberry jam

- Shelf: Pantry. Locator: `hass/content/products.json` L1066 (`id` photo-product-010, field `description`). Maker key: “Cal Poly”.
- **S1** “Blackberry jam, from Cal Poly’s food program in San Luis Obispo.”
  - Clause: made by Cal Poly’s food program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
  - Clause: San Luis Obispo location — **recorded support**
    - maker-location record: `hass/content/makers.json` L42, maker "Cal Poly", place "San Luis Obispo, California"

#### photo-product-011 — Sweet Hickory BBQ sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1077 (`id` photo-product-011, field `description`). Maker key: “Cal Poly”.
- **S1** “Sweet Hickory BBQ sauce from Cal Poly.”
  - Clause: made by Cal Poly — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.

#### photo-product-012 — Cal Poly chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1088 (`id` photo-product-012, field `description`). Maker key: “Cal Poly”.
- **S1** “Cal Poly, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.

#### photo-product-013 — Original hot sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1099 (`id` photo-product-013, field `description`). Maker key: “Cayucos”.
- **S1** “Cayucos hot sauce, from a coast that knows what to do with a fish taco.”
  - Clause: from Cayucos — **recorded support**
    - maker-location record: `hass/content/makers.json` L126, maker "Cayucos", place "Cayucos, California"
    - secondary context only (maker story, not independent): `hass/content/makers.json` L127, maker "Cayucos": “Cayucos Hot Sauce was born in a little shack across from the beach on Highway 1.”
    - Note: Maker location; no Cayucos query exists in the research log.

#### photo-product-041 — Stepladder avocado blossom honey

- Shelf: Pantry. Locator: `hass/content/products.json` L1132 (`id` photo-product-041, field `description`). Maker key: “Stepladder”.
- **S1** “Avocado blossom honey from Stepladder in Cambria.”
  - Clause: avocado blossom honey (floral source) — **no source found**
  - Clause: made or sold by Stepladder — **no source found**
    - Note: The Stepladder record mentions cheese only; no honey is recorded for Stepladder.
  - Clause: Cambria location — **recorded support**
    - maker-location record: `hass/content/makers.json` L12, maker "Stepladder", place "Cambria, California"
    - Note: Location of the maker.

#### photo-product-042 — Big Sur Honey Company honey

- Shelf: Pantry. Locator: `hass/content/products.json` L1143 (`id` photo-product-042, field `description`). Maker key: “Big Sur Honey Company”.
- **S1** “Honey from a family apiary in Big Sur.”
  - Clause: family apiary — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “brought to you by a small family apiary”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Big Sur Honey Co. is a small family operation, run by Dylan and Jessie”
  - Clause: in Big Sur — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Pristine honey gathered from Big Sur wildflowers”
    - maker-location record: `hass/content/makers.json` L72, maker "Big Sur Honey Company", place "Big Sur, California"
- **S2** “Raw and unfiltered, with a place behind the jar.”
  - Clause: raw — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Never pasteurized to prevent crystallization.”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Our honey is never heated, force-filtered, or diluted with inferior sweeteners.”
    - Note: Maker-level statement, not a label check of this jar.
  - Clause: unfiltered — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Unfiltered”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L20 (query “Big Sur Honey Company official story”, result record #4): “Never force filtered”
    - Note: The maker says “never force filtered”; the heading says “Unfiltered”.

#### photo-product-043 — Sunshine Estate olive oil

- Shelf: Pantry. Locator: `hass/content/products.json` L1154 (`id` photo-product-043, field `description`). Maker key: “Sunshine Olive”.
- **S1** “Estate olive oil from Sunshine in Templeton.”
  - Clause: Sunshine, Templeton — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L16 (query “Sunshine olive oil official Spanish Oaks”, result record #3): “Sunshine Olive Oil | Templeton, CA”
    - maker-location record: `hass/content/makers.json` L66, maker "Sunshine Olive", place "Templeton, California"
  - Clause: estate (grown and pressed by the producer) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L67, maker "Sunshine Olive": “The photographed bottles name the estate and olive variety”
    - checked absence: `storefront-mockup/producer-research-log.json` L16 (query “Sunshine olive oil official Spanish Oaks”) does not contain “estate”
    - Note: The log result contains no “estate”; the maker story refers to a photograph that is not in this record.

#### photo-product-044 — Dried mushrooms

- Shelf: Pantry. Locator: `hass/content/products.json` L1165 (`id` photo-product-044, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried mushrooms are a pantry shortcut to a deeper meal.”
  - Clause: mushrooms sold dried (state/process; made or grown by Mighty Cap) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: The story does not mention drying; the record does not say which mushroom species the jar holds.

#### photo-product-045 — Sunshine Olive Spanish Oaks Picual olive oil

- Shelf: Pantry. Locator: `hass/content/products.json` L1176 (`id` photo-product-045, field `description`). Maker key: “Sunshine Olive”.
- **S1** “Picual olive oil from Sunshine Olive in Templeton.”
  - Clause: Picual olive oil from Sunshine — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L16 (query “Sunshine olive oil official Spanish Oaks”, result record #3): “Sunshine Spanish Oaks Picual (Organic)”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L16 (query “Sunshine olive oil official Spanish Oaks”, result record #3): “Our Picual is a bold, balanced extra virgin olive oil”
  - Clause: Templeton location — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L16 (query “Sunshine olive oil official Spanish Oaks”, result record #3): “Sunshine Olive Oil | Templeton, CA”
    - maker-location record: `hass/content/makers.json` L66, maker "Sunshine Olive", place "Templeton, California"

#### photo-product-046 — Dried lion’s mane mushrooms

- Shelf: Pantry. Locator: `hass/content/products.json` L1187 (`id` photo-product-046, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried lion’s mane from Mighty Cap in Paso Robles.”
  - Clause: dried lion’s mane made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
  - Clause: Paso Robles location — **recorded support**
    - maker-location record: `hass/content/makers.json` L84, maker "Mighty Cap Mushrooms", place "Paso Robles, California"
    - Note: Maker location.

#### photo-product-047 — Dried maitake mushrooms

- Shelf: Pantry. Locator: `hass/content/products.json` L1198 (`id` photo-product-047, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried maitake from Mighty Cap in Paso Robles.”
  - Clause: dried maitake made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
  - Clause: Paso Robles location — **recorded support**
    - maker-location record: `hass/content/makers.json` L84, maker "Mighty Cap Mushrooms", place "Paso Robles, California"
    - Note: Maker location.

#### photo-product-052 — Maple Valley dark and robust maple syrup

- Shelf: Pantry. Locator: `hass/content/products.json` L1209 (`id` photo-product-052, field `description`). Maker key: “Maple Valley”.
- **S1** “Organic dark and robust maple syrup from a Wisconsin cooperative.”
  - Clause: organic — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L32 (query “Maple Valley cooperative official about”, result record #7): “Maple Valley is committed to producing delicious, small-batch, high-quality certified organic”
    - Note: Maker-level; the organic badge itself is audited under AV1052-14.
  - Clause: dark and robust grade — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L115, maker "Maple Valley": “Dark and robust means a proper maple presence”
    - checked absence: `storefront-mockup/producer-research-log.json` L32 (query “Maple Valley cooperative official about”) does not contain “dark”, “robust”
  - Clause: from a Wisconsin cooperative — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L32 (query “Maple Valley cooperative official about”, result record #7): “a cooperative in 2007”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L32 (query “Maple Valley cooperative official about”, result record #7): “the rural town of Cashton in southwest Wisconsin”
    - maker-location record: `hass/content/makers.json` L114, maker "Maple Valley", place "Cashton, Wisconsin"
    - Note: Cooperative and bottling office are recorded in Wisconsin; the same record says farmer members tap trees in Wisconsin, Minnesota and other states, so the state of this syrup’s trees is not recorded.

#### photo-product-053 — Sean's muesli munch

- Shelf: Pantry. Locator: `hass/content/products.json` L1220 (`id` photo-product-053, field `description`). Maker key: “Sean's”.
- **S1** “Muesli Munch from San Luis Obispo.”
  - Clause: Muesli Munch is Sean’s product — **no source found**
    - checked absence: `storefront-mockup/producer-research-log.json` L76 (query “Seans Muesli Munch official about”) does not contain “Sean”
    - Note: The query “Seans Muesli Munch official about” returned unrelated Munch/Munchilicious pages (a Trader Joe’s blog, an Indian muesli brand) and a CCOF listing for “Muesli Munch, LLC”; nothing ties them to Sean’s, so they are not treated as evidence.
  - Clause: from San Luis Obispo — **partial support**
    - maker-location record: `hass/content/makers.json` L144, maker "Sean's", place "San Luis Obispo, California"
    - checked absence: `storefront-mockup/producer-research-log.json` L76 (query “Seans Muesli Munch official about”) does not contain “San Luis Obispo”
    - Note: Only the maker place record names San Luis Obispo; the research result does not.

#### photo-product-054 — Massa Organics brown rice

- Shelf: Pantry. Locator: `hass/content/products.json` L1231 (`id` photo-product-054, field `description`). Maker key: “Massa Organics”.
- **S1** “Organic brown rice grown near Chico.”
  - Clause: organic — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L24 (query “Massa Organics official about”, result record #5): “We started as a small organic rice farm in 2002”
    - Note: Farm-level; the organic badge itself is audited under AV1052-14.
  - Clause: brown rice — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L79, maker "Massa Organics": “Their medium-grain brown rice”
  - Clause: grown near Chico — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L24 (query “Massa Organics official about”, result record #5): “Located near Chico in the fertile Sacramento Valley of Northern California”
    - maker-location record: `hass/content/makers.json` L78, maker "Massa Organics", place "Near Chico, California"

#### photo-product-088 — Cranberry Orange granola

- Shelf: Pantry. Locator: `hass/content/products.json` L1264 (`id` photo-product-088, field `description`). Maker key: “Ocean Ranch”.
- **S1** “Cranberry Orange in a handmade organic granola.”
  - Clause: handmade — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “making granola by hand in small batches”
  - Clause: organic — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “Organic ingredients and flavors”
    - Note: Organic badge audited under AV1052-14.
  - Clause: flavour ingredients (cranberry orange) — **no source found**

#### photo-product-089 — Oaxacan Chocolate granola

- Shelf: Pantry. Locator: `hass/content/products.json` L1275 (`id` photo-product-089, field `description`). Maker key: “Ocean Ranch”.
- **S1** “Oaxacan Chocolate in a handmade organic granola.”
  - Clause: handmade — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “making granola by hand in small batches”
  - Clause: organic — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “Organic ingredients and flavors”
    - Note: Organic badge audited under AV1052-14.
  - Clause: flavour ingredients (oaxacan chocolate) — **no source found**

#### photo-product-090 — Lemon Blueberry granola

- Shelf: Pantry. Locator: `hass/content/products.json` L1286 (`id` photo-product-090, field `description`). Maker key: “Ocean Ranch”.
- **S1** “Lemon Blueberry in a handmade organic granola.”
  - Clause: handmade — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “making granola by hand in small batches”
  - Clause: organic — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “Organic ingredients and flavors”
    - Note: Organic badge audited under AV1052-14.
  - Clause: flavour ingredients (lemon blueberry) — **no source found**

#### photo-product-091 — Turmeric Goji Berry granola

- Shelf: Pantry. Locator: `hass/content/products.json` L1297 (`id` photo-product-091, field `description`). Maker key: “Ocean Ranch”.
- **S1** “Turmeric Goji Berry in a handmade organic granola.”
  - Clause: handmade — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “making granola by hand in small batches”
  - Clause: organic — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L25, maker "Ocean Ranch": “Organic ingredients and flavors”
    - Note: Organic badge audited under AV1052-14.
  - Clause: flavour ingredients (turmeric goji berry) — **no source found**

#### photo-product-093 — Avocado Shack (Hands)

- Shelf: Pantry. Locator: `hass/content/products.json` L1308 (`id` photo-product-093, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S1** “Avocado Shack coffee for the kitchen counter.”
  - Clause: Avocado Shack coffee (roasted in Atascadero by Joebella) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L55, maker "Joebella / Avocado Shack": “The Shack’s coffee selection puts that nearby craft within reach of your own morning routine.”
    - Note: The description names only Avocado Shack; the maker key reads “Joebella / Avocado Shack”. Nothing recorded states who roasted this product.

#### photo-product-105 — Sunshine Peach preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1319 (`id` photo-product-105, field `description`). Maker key: “Linn's”.
- **S1** “Sunshine peach preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: peach (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: peach as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L3: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9707.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-106 — Strawberry preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1330 (`id` photo-product-106, field `description`). Maker key: “Linn's”.
- **S1** “Strawberry preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: strawberry (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: strawberry as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L22: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9707.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-107 — California Apricot preserves

- Shelf: Pantry. Locator: `hass/content/products.json` L1341 (`id` photo-product-107, field `description`). Maker key: “Linn's”.
- **S1** “California apricot preserves for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: apricot (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: apricot as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s.
  - Clause: apricots from California (origin) — **partial support**
    - maker-location record: `hass/content/makers.json` L30, maker "Linn's", place "Cambria, California"
    - Note: Maker location is Cambria, California; the origin of the apricots is not recorded.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L41: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9707.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-108 — Blood Orange marmalade

- Shelf: Pantry. Locator: `hass/content/products.json` L1352 (`id` photo-product-108, field `description`). Maker key: “Linn's”.
- **S1** “Blood orange marmalade for buttered toast, a bowl of yogurt, or a plain cake that deserves a little company.”
  - Clause: blood orange (marmalade) (product identity as stated in the sentence) made by Linn’s — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L4 (query “Linns Cambria official about farm”, result record #0): “creating Linn's Fruit Preserves”
    - secondary context only (maker story, not independent): `hass/content/makers.json` L31, maker "Linn's": “These preserves belong on real bread, with real butter.”
    - Note: Maker-level: the extract names Linn’s fruit preserves but not this flavour or jar.
  - Clause: blood orange (marmalade) as the fruit ingredient — **no source found**
    - Note: No record names this fruit for Linn’s. The only “blood orange” hit in the same search result is a restaurant dressing, not Linn’s.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L60: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9707.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-109 — Peppermint Crunch chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1363 (`id` photo-product-109, field `description`). Maker key: “Cal Poly”.
- **S1** “Peppermint Crunch, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L79: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-110 — Cookies and Cream chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1374 (`id` photo-product-110, field `description`). Maker key: “Cal Poly”.
- **S1** “Cookies and Cream, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L98: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-111 — Zesty Orange chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1385 (`id` photo-product-111, field `description`). Maker key: “Cal Poly”.
- **S1** “Zesty Orange, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L117: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-112 — Dark chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1396 (`id` photo-product-112, field `description`). Maker key: “Cal Poly”.
- **S1** “Dark, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L136: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-113 — Milk chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1407 (`id` photo-product-113, field `description`). Maker key: “Cal Poly”.
- **S1** “Milk, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L155: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-114 — Lemon Bar white chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1418 (`id` photo-product-114, field `description`). Maker key: “Cal Poly”.
- **S1** “Lemon Bar white, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L174: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-115 — Habanero chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1429 (`id` photo-product-115, field `description`). Maker key: “Cal Poly”.
- **S1** “Habanero, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L193: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-116 — S’mores chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1440 (`id` photo-product-116, field `description`). Maker key: “Cal Poly”.
- **S1** “S’mores, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L212: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-117 — Lemon Lavender white chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1451 (`id` photo-product-117, field `description`). Maker key: “Cal Poly”.
- **S1** “Lemon Lavender white, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L231: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-118 — Birthday Cake chocolate

- Shelf: Pantry. Locator: `hass/content/products.json` L1462 (`id` photo-product-118, field `description`). Maker key: “Cal Poly”.
- **S1** “Birthday Cake, made by Cal Poly’s student chocolate program.”
  - Clause: made by Cal Poly’s student chocolate program — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L250: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-119 — Mustang Kick BBQ sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1473 (`id` photo-product-119, field `description`). Maker key: “Cal Poly”.
- **S1** “Cal Poly’s Mustang Kick belongs beside the grill.”
  - Clause: made by Cal Poly — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L43, maker "Cal Poly": “Students work on products from cheese and chocolate to jam and barbecue sauce”
    - Note: No Cal Poly query exists in the research log.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L269: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9710.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-120 — Carrot Habanero hot sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1484 (`id` photo-product-120, field `description`). Maker key: “Cayucos”.
- **S1** “Carrot and habanero: sweetness and heat in the same bottle.”
  - Clause: contains carrot and habanero (ingredients) — **no source found**
    - Note: The October note records only a photographed product.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L288: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9711.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-121 — Green hot sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1495 (`id` photo-product-121, field `description`). Maker key: “Cayucos”.
- **S1** “Green hot sauce from Cayucos.”
  - Clause: from Cayucos — **recorded support**
    - maker-location record: `hass/content/makers.json` L126, maker "Cayucos", place "Cayucos, California"
    - Note: Maker location.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L307: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9711.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-134 — Dried morels

- Shelf: Pantry. Locator: `hass/content/products.json` L1506 (`id` photo-product-134, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried morels from Mighty Cap.”
  - Clause: dried morels made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L554: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9724.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-135 — Dried shiitake

- Shelf: Pantry. Locator: `hass/content/products.json` L1517 (`id` photo-product-135, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried shiitake from Mighty Cap.”
  - Clause: dried shiitake made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L573: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9724.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-136 — Dried king oyster mushrooms

- Shelf: Pantry. Locator: `hass/content/products.json` L1528 (`id` photo-product-136, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Dried king oyster mushrooms from Mighty Cap.”
  - Clause: dried king oyster mushrooms made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L592: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9724.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-137 — Mushroom Umami Sauce

- Shelf: Pantry. Locator: `hass/content/products.json` L1539 (`id` photo-product-137, field `description`). Maker key: “Mighty Cap Mushrooms”.
- **S1** “Mushroom Umami Sauce from Mighty Cap in Paso Robles.”
  - Clause: Mushroom Umami Sauce made or grown by Mighty Cap — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L85, maker "Mighty Cap Mushrooms": “a gourmet mushroom farm in Paso Robles”
    - Note: No Mighty Cap query exists in the research log; the story does not mention drying or sauce.
  - Clause: Paso Robles location — **recorded support**
    - maker-location record: `hass/content/makers.json` L84, maker "Mighty Cap Mushrooms", place "Paso Robles, California"
    - Note: Maker location.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L611: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9724.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-138 — Crimson lentils

- Shelf: Pantry. Locator: `hass/content/products.json` L1550 (`id` photo-product-138, field `description`). Maker key: none.
- **S1** “A quick-cooking pulse for soup, dal, or the base of a simple dinner.”
  - Clause: a pulse (lentil) that cooks quickly — **no source found**
    - Note: The October note records only a photographed product with no brand; cooking time is not recorded.
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L630: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9728.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

### Drinks & coffee (15 active products)

#### photo-product-007 — Fair Hills Farm apple juice

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1704 (`id` photo-product-007, field `description`). Maker key: “Fair Hills Farm”.
- **S1** “Apple juice from Fair Hills Farm in San Miguel.”
  - Clause: apple juice made by Fair Hills Farm — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L19, maker "Fair Hills Farm": “Fair Hills presses apples into unfiltered juice”
    - Note: No Fair Hills query exists in the research log.
  - Clause: San Miguel location — **recorded support**
    - maker-location record: `hass/content/makers.json` L18, maker "Fair Hills Farm", place "San Miguel, California"

#### photo-product-014 — Zero non-alcoholic cider

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1715 (`id` photo-product-014, field `description`). Maker key: none.
- **S1** “A cider for the moments when you want a good drink without the alcohol.”
  - Clause: non-alcoholic — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L64 (query “SLO Cider official about Zero”, result record #15): “We make a Non-Alcoholic Cider”
    - Note: The record says SLO Cider makes a non-alcoholic cider. Nothing records that this “Zero” product is that cider; the same result also lists an unrelated “Zero Alcohol Cider” (a Peckhams 4-pack), so the name alone does not identify the maker.
  - Clause: is a cider — **no source found**

#### photo-product-019 — Organic beet juice

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1726 (`id` photo-product-019, field `description`). Maker key: “Love Beets”.
- **S1** “Organic beet juice brings the earthy side of the garden into the glass.”
  - Clause: organic beet juice — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L68 (query “Love Beets official about us”, result record #16): “all natural beet juices”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L68 (query “Love Beets official about us”, result record #16): “Organic Cooked Beets”
    - Note: Maker-level: the record shows a Love Beets juice line and organic cooked beets, not an organic juice label; one juice item in the same result is dated “Published: 11.7 years ago”. Organic badge audited under AV1052-14.

#### photo-product-048 — Fair Hills Farm chamomile tea

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1737 (`id` photo-product-048, field `description`). Maker key: “Fair Hills Farm”.
- **S1** “Chamomile tea with Fair Hills Farm apple juice.”
  - Clause: contains Fair Hills Farm apple juice — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L19, maker "Fair Hills Farm": “uses orchard apple juice to gently sweeten its teas”
  - Clause: chamomile tea (named ingredients) — **no source found**

#### photo-product-049 — Fair Hills Farm black tea

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1748 (`id` photo-product-049, field `description`). Maker key: “Fair Hills Farm”.
- **S1** “Black tea meets Fair Hills Farm apple juice.”
  - Clause: contains Fair Hills Farm apple juice — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L19, maker "Fair Hills Farm": “uses orchard apple juice to gently sweeten its teas”
  - Clause: black tea (named ingredients) — **no source found**

#### photo-product-050 — Fair Hills Farm cinnamon black tea

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1759 (`id` photo-product-050, field `description`). Maker key: “Fair Hills Farm”.
- **S1** “Cinnamon, black tea, and Fair Hills Farm apple juice.”
  - Clause: contains Fair Hills Farm apple juice — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L19, maker "Fair Hills Farm": “uses orchard apple juice to gently sweeten its teas”
  - Clause: cinnamon black tea (named ingredients) — **no source found**

#### photo-product-051 — Ginger black tea

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1770 (`id` photo-product-051, field `description`). Maker key: “Fair Hills Farm”.
- **S1** “Ginger gives black tea a sharp little edge.”
  - Clause: contains ginger (ingredient) — **no source found**

#### photo-product-083 — Albino Coast Redwood Blend

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1781 (`id` photo-product-083, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

#### photo-product-084 — Cone Peak Blend

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1792 (`id` photo-product-084, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

#### photo-product-085 — Dream Girl Decaf

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1803 (`id` photo-product-085, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S1** “Dream Girl Decaf.”
  - Clause: decaffeinated — **no source found**
    - checked absence: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”) does not contain “decaf”
    - Note: The word comes from the product name only.

#### photo-product-086 — Peace Be With You Blend

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1814 (`id` photo-product-086, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

#### photo-product-087 — Packer’s Blend coffee bags

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1825 (`id` photo-product-087, field `description`). Maker key: “Corberosa”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Corberosa (product type) — **no source found (secondary context only)**
    - secondary context only (maker story, not independent): `hass/content/makers.json` L61, maker "Corberosa": “Corberosa roasts coffee on a moving bed of hot air”
    - Note: No Corberosa query exists in the research log; the Packer’s Blend is not named in any record.

#### photo-product-092 — Avocado Shack Blend (Hut)

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1836 (`id` photo-product-092, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

#### photo-product-094 — Cass Hill Blend

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1847 (`id` photo-product-094, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

#### photo-product-095 — Cambria Blend

- Shelf: Drinks & coffee. Locator: `hass/content/products.json` L1858 (`id` photo-product-095, field `description`). Maker key: “Joebella / Avocado Shack”.
- **S2** “Coffee for a real pause in the day: grind fresh when possible, brew with care, and give the first cup a minute of your attention.”
  - Clause: product is coffee, roasted by Joebella / Avocado Shack (product type) — **partial support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L12 (query “Joebella coffee official about”, result record #2): “we’ve been roasting small-batch, organic coffee right here in Atascadero”
    - Note: Maker-level; the named blend is not recorded, and “grind fresh” implies whole beans, which no record states.

### Bread (4 active products)

#### photo-product-015 — Brian's sourdough bread

- Shelf: Bread. Locator: `hass/content/products.json` L956 (`id` photo-product-015, field `description`). Maker key: “Brian's”.
- **S1** “Sourdough from Brian’s in Atascadero.”
  - Clause: sourdough — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “Brian's sourdough bread speaks for itself in quality and flavor.”
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “Starter is a natural yeast and is the base of sourdough bread.”
  - Clause: Brian’s in Atascadero — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “4005 Traffic Way, Atascadero, CA 93422”
    - maker-location record: `hass/content/makers.json` L132, maker "Brian's", place "Atascadero, California"

#### photo-product-122 — Rye bread

- Shelf: Bread. Locator: `hass/content/products.json` L967 (`id` photo-product-122, field `description`). Maker key: “Brian's”.
- **S1** “Rye bread from Brian’s in Atascadero.”
  - Clause: rye bread — **no source found**
    - checked absence: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”) does not contain “rye”
    - Note: The Brian’s extract lists Sourdough, Cracked Wheat and Rosemary with Olive Oil only.
  - Clause: Brian’s in Atascadero — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “4005 Traffic Way, Atascadero, CA 93422”
    - maker-location record: `hass/content/makers.json` L132, maker "Brian's", place "Atascadero, California"
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L326: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9713.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-123 — Rosemary Sourdough with Olive Oil

- Shelf: Bread. Locator: `hass/content/products.json` L978 (`id` photo-product-123, field `description`). Maker key: “Brian's”.
- **S1** “Rosemary and olive oil in Brian’s sourdough.”
  - Clause: Brian’s sourdough with rosemary and olive oil — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “Sliced Rosemary w/ Olive Oil Sourdough”
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L345: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9713.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

#### photo-product-124 — Cracked Wheat Sourdough

- Shelf: Bread. Locator: `hass/content/products.json` L989 (`id` photo-product-124, field `description`). Maker key: “Brian's”.
- **S1** “Cracked wheat sourdough from Brian’s.”
  - Clause: cracked wheat sourdough from Brian’s — **recorded support**
    - recorded producer extract: `storefront-mockup/producer-research-log.json` L72 (query “Brians artisan bread official about”, result record #17): “Sliced Cracked Wheat Sourdough”
- October photo-review record (other records consulted): `storefront-mockup/completion-new-products.json` L364: status “Distinct label or product visible in original photograph; owner confirmation remains in research file”; evidence “Original photograph IMG_9713.jpg”; notes “Selling units, price and availability remain development assumptions.”. This proves only that a distinct label or product was recorded as visible in the photograph; it records no origin, ingredient or process. The original photograph was not inspected, and the generated product image is not label evidence.

### Flowers (1 active products)

No description on this shelf contains a qualifying checkable-fact sentence (reasons in the coverage appendix).

## Coverage appendix

Every active product exactly once, in shelf and site order.

| Shelf | Product id | Name | Result | Sentence numbers or exclusion reason |
|---|---|---|---|---|
| Fruit | photo-product-001 | Hass avocado | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-016 | Oranges | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-017 | Lemons | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-056 | Strawberries | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-057 | Raspberries | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-058 | Blueberries | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-059 | Golden raspberries | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-078 | Watermelon | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-080 | Honeydew-type melon | excluded | appearance and serving suggestion only |
| Fruit | photo-product-081 | Keitt mango | excluded | appearance/ripeness advice only (green skin, golden flesh); no origin stated |
| Fruit | photo-product-096 | Passion fruit | excluded | appearance and serving suggestion only |
| Fruit | photo-product-097 | Figs | excluded | taste, texture or cooking/serving suggestion only |
| Fruit | photo-product-098 | Blackberries | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-018 | Montaña de Oro Sea Salt tortilla chips | included | S1 |
| Vegetables | photo-product-060 | Fennel | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-061 | Broccoli | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-062 | Romaine lettuce | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-063 | Bok choy | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-064 | Leeks | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-065 | Celery | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-066 | Bunched carrots | excluded | “eat one raw” is advice (see selection rule); no state of the product asserted |
| Vegetables | photo-product-067 | Potatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-068 | Lettuce | excluded | “Fresh” is a quality word and the rest is salad/dressing advice; no origin, state or process stated |
| Vegetables | photo-product-069 | Spring Greens | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-070 | Wild Arugula | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-071 | Mushrooms | excluded | “Fresh” is a quality word and the rest is cooking advice; no origin, state or process stated |
| Vegetables | photo-product-072 | Sunflower microgreens | excluded | name restated with “fresh” and serving advice; no origin or growing method stated |
| Vegetables | photo-product-073 | Ginger | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-074 | Turmeric | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-075 | Eggplant | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-076 | Peppers | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-077 | Tomatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-079 | Cantaloupe | excluded | appearance and serving suggestion only |
| Vegetables | photo-product-099 | Garlic | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-100 | Shallots | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-101 | Yellow onions | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-102 | Red onions | excluded | taste of the onion raw and cooked, plus cooking advice; no product-specific fact |
| Vegetables | photo-product-103 | Radicchio | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-104 | Purple daikon | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-145 | Gold potatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-146 | Red potatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-147 | Purple potatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-148 | Loose carrots | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-149 | Green cabbage | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-150 | Lion’s mane mushrooms | excluded | appearance and cooking advice only |
| Vegetables | photo-product-151 | King oyster mushrooms | excluded | species name restated with appearance and cooking advice; no state, origin or process stated |
| Vegetables | photo-product-152 | Shiitake mushrooms | excluded | species name restated with appearance and cooking advice; no state, origin or process stated |
| Vegetables | photo-product-153 | Maitake mushrooms | excluded | species name restated with appearance and cooking advice; no state, origin or process stated |
| Vegetables | photo-product-154 | Chanterelle mushrooms | excluded | species name restated with appearance and cooking advice; no state, origin or process stated |
| Vegetables | photo-product-155 | Lobster mushrooms | excluded | colour and cooking advice only |
| Vegetables | photo-product-156 | Crimini mushrooms | excluded | species name restated with appearance and cooking advice; no state, origin or process stated |
| Vegetables | photo-product-157 | Cilantro microgreens | excluded | name restated with “fresh” and serving advice; no origin or growing method stated |
| Vegetables | photo-product-158 | Radish Mix microgreens | excluded | name restated with “fresh” and serving advice; no origin or growing method stated |
| Vegetables | photo-product-159 | Arugula microgreens | excluded | name restated with “fresh” and serving advice; no origin or growing method stated |
| Vegetables | photo-product-160 | Broccoli microgreens | excluded | name restated with “fresh” and serving advice; no origin or growing method stated |
| Vegetables | photo-product-161 | Horseradish | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-162 | Jalapeños | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-163 | Sweet peppers | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-164 | Red bell peppers | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-165 | Poblano peppers | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-166 | Zucchini | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-167 | Green onions | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-168 | San Marzano tomatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-169 | Cherry tomatoes | excluded | taste, texture or cooking/serving suggestion only |
| Vegetables | photo-product-170 | Sun Gold tomatoes | excluded | taste, texture or cooking/serving suggestion only |
| Dairy & cheese | photo-product-025 | Straus half-and-half | included | S1 |
| Dairy & cheese | photo-product-026 | Straus heavy whipping cream | included | S1 |
| Dairy & cheese | photo-product-027 | Organic whole milk | included | S2 |
| Dairy & cheese | photo-product-028 | Straus butter | excluded | opinion (“good butter”) and cooking advice; no process or ingredient stated |
| Dairy & cheese | photo-product-029 | Ragged Point cheese | included | S1 |
| Dairy & cheese | photo-product-030 | Stepladder cultured butter | included | S1 |
| Dairy & cheese | photo-product-033 | Stepladder Rocky Butte cheese | included | S1 |
| Dairy & cheese | photo-product-034 | Stepladder Bixby cheese | included | S1 |
| Dairy & cheese | photo-product-035 | Chèvre | included | S1 |
| Dairy & cheese | photo-product-037 | Cal Poly chipotle cheddar | included | S1 |
| Dairy & cheese | photo-product-038 | Cal Poly white cheddar | included | S1 |
| Dairy & cheese | photo-product-039 | Cal Poly Highland cheddar | included | S1 |
| Dairy & cheese | photo-product-125 | Whole Milk Plain European Style yogurt | included | S1 |
| Dairy & cheese | photo-product-126 | Greek Whole Milk Plain yogurt | excluded | texture and serving advice only; no process or ingredient stated |
| Dairy & cheese | photo-product-127 | Sour cream | included | S1 |
| Dairy & cheese | photo-product-128 | Big Sur cheese | included | S1 |
| Dairy & cheese | photo-product-129 | Marinated Fromage Blanc | included | S1 |
| Dairy & cheese | photo-product-130 | Gouda | included | S1 |
| Dairy & cheese | photo-product-131 | Hatch Chile Sierra Jack | included | S1 |
| Dairy & cheese | photo-product-132 | Habanero Sierra Jack | included | S1 |
| Eggs | photo-product-024 | Cal Poly eggs | excluded | cooking advice only; the egg source is in the product name, not a description sentence |
| Meat | photo-product-021 | Alle-Pia Calabrese salamini | included | S1 |
| Meat | photo-product-022 | Alle-Pia guanciale | included | S1 |
| Meat | photo-product-023 | Alle-Pia mortadella | included | S1 |
| Pantry | photo-product-002 | Linn's triple berry preserves | included | S1 |
| Pantry | photo-product-003 | Linn's blueberry preserves | included | S1 |
| Pantry | photo-product-004 | Linn's boysenberry preserves | included | S1 |
| Pantry | photo-product-005 | Linn's orange marmalade | included | S1 |
| Pantry | photo-product-008 | Cal Poly strawberry jam | included | S1 |
| Pantry | photo-product-009 | Cal Poly raspberry jam | included | S1 |
| Pantry | photo-product-010 | Cal Poly blackberry jam | included | S1 |
| Pantry | photo-product-011 | Sweet Hickory BBQ sauce | included | S1 |
| Pantry | photo-product-012 | Cal Poly chocolate | included | S1 |
| Pantry | photo-product-013 | Original hot sauce | included | S1 |
| Pantry | photo-product-031 | Guacamole | excluded | serving scene; “Avocado” is a list opener, not an ingredient statement |
| Pantry | photo-product-032 | Garlic pesto | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-041 | Stepladder avocado blossom honey | included | S1 |
| Pantry | photo-product-042 | Big Sur Honey Company honey | included | S1, S2 |
| Pantry | photo-product-043 | Sunshine Estate olive oil | included | S1 |
| Pantry | photo-product-044 | Dried mushrooms | included | S1 |
| Pantry | photo-product-045 | Sunshine Olive Spanish Oaks Picual olive oil | included | S1 |
| Pantry | photo-product-046 | Dried lion’s mane mushrooms | included | S1 |
| Pantry | photo-product-047 | Dried maitake mushrooms | included | S1 |
| Pantry | photo-product-052 | Maple Valley dark and robust maple syrup | included | S1 |
| Pantry | photo-product-053 | Sean's muesli munch | included | S1 |
| Pantry | photo-product-054 | Massa Organics brown rice | included | S1 |
| Pantry | photo-product-055 | Cashews | excluded | snack and toasting advice naming the nut only; no origin or process stated |
| Pantry | photo-product-082 | Artisan short-cut pasta | excluded | pasta-shape and sauce advice; no ingredient, maker or process stated |
| Pantry | photo-product-088 | Cranberry Orange granola | included | S1 |
| Pantry | photo-product-089 | Oaxacan Chocolate granola | included | S1 |
| Pantry | photo-product-090 | Lemon Blueberry granola | included | S1 |
| Pantry | photo-product-091 | Turmeric Goji Berry granola | included | S1 |
| Pantry | photo-product-093 | Avocado Shack (Hands) | included | S1 |
| Pantry | photo-product-105 | Sunshine Peach preserves | included | S1 |
| Pantry | photo-product-106 | Strawberry preserves | included | S1 |
| Pantry | photo-product-107 | California Apricot preserves | included | S1 |
| Pantry | photo-product-108 | Blood Orange marmalade | included | S1 |
| Pantry | photo-product-109 | Peppermint Crunch chocolate | included | S1 |
| Pantry | photo-product-110 | Cookies and Cream chocolate | included | S1 |
| Pantry | photo-product-111 | Zesty Orange chocolate | included | S1 |
| Pantry | photo-product-112 | Dark chocolate | included | S1 |
| Pantry | photo-product-113 | Milk chocolate | included | S1 |
| Pantry | photo-product-114 | Lemon Bar white chocolate | included | S1 |
| Pantry | photo-product-115 | Habanero chocolate | included | S1 |
| Pantry | photo-product-116 | S’mores chocolate | included | S1 |
| Pantry | photo-product-117 | Lemon Lavender white chocolate | included | S1 |
| Pantry | photo-product-118 | Birthday Cake chocolate | included | S1 |
| Pantry | photo-product-119 | Mustang Kick BBQ sauce | included | S1 |
| Pantry | photo-product-120 | Carrot Habanero hot sauce | included | S1 |
| Pantry | photo-product-121 | Green hot sauce | included | S1 |
| Pantry | photo-product-134 | Dried morels | included | S1 |
| Pantry | photo-product-135 | Dried shiitake | included | S1 |
| Pantry | photo-product-136 | Dried king oyster mushrooms | included | S1 |
| Pantry | photo-product-137 | Mushroom Umami Sauce | included | S1 |
| Pantry | photo-product-138 | Crimson lentils | included | S1 |
| Pantry | photo-product-139 | Red beans | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-140 | Black beans | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-141 | Chickpeas | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-142 | Almonds | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-143 | Pistachios | excluded | taste, texture or cooking/serving suggestion only |
| Pantry | photo-product-144 | Trail mix | excluded | generic remark about nuts and fruit as a snack; does not state this product’s contents |
| Pantry | photo-product-171 | Radiatori pasta | excluded | pasta-shape and sauce advice; no ingredient, maker or process stated |
| Pantry | photo-product-172 | Rigatoni pasta | excluded | pasta-shape and sauce advice; no ingredient, maker or process stated |
| Pantry | photo-product-173 | Casarecce pasta | excluded | pasta-shape and sauce advice; no ingredient, maker or process stated |
| Pantry | photo-product-174 | Conchiglie pasta | excluded | pasta-shape and sauce advice; no ingredient, maker or process stated |
| Drinks & coffee | photo-product-007 | Fair Hills Farm apple juice | included | S1 |
| Drinks & coffee | photo-product-014 | Zero non-alcoholic cider | included | S1 |
| Drinks & coffee | photo-product-019 | Organic beet juice | included | S1 |
| Drinks & coffee | photo-product-048 | Fair Hills Farm chamomile tea | included | S1 |
| Drinks & coffee | photo-product-049 | Fair Hills Farm black tea | included | S1 |
| Drinks & coffee | photo-product-050 | Fair Hills Farm cinnamon black tea | included | S1 |
| Drinks & coffee | photo-product-051 | Ginger black tea | included | S1 |
| Drinks & coffee | photo-product-083 | Albino Coast Redwood Blend | included | S2 |
| Drinks & coffee | photo-product-084 | Cone Peak Blend | included | S2 |
| Drinks & coffee | photo-product-085 | Dream Girl Decaf | included | S1 |
| Drinks & coffee | photo-product-086 | Peace Be With You Blend | included | S2 |
| Drinks & coffee | photo-product-087 | Packer’s Blend coffee bags | included | S2 |
| Drinks & coffee | photo-product-092 | Avocado Shack Blend (Hut) | included | S2 |
| Drinks & coffee | photo-product-094 | Cass Hill Blend | included | S2 |
| Drinks & coffee | photo-product-095 | Cambria Blend | included | S2 |
| Bread | photo-product-015 | Brian's sourdough bread | included | S1 |
| Bread | photo-product-122 | Rye bread | included | S1 |
| Bread | photo-product-123 | Rosemary Sourdough with Olive Oil | included | S1 |
| Bread | photo-product-124 | Cracked Wheat Sourdough | included | S1 |
| Flowers | photo-product-006 | Mixed flower bouquet | excluded | taste, texture or cooking/serving suggestion only |

## Local review checks (named in the card, run on this report before the PR)

- activeCoverageAndShelfOrder: the appendix lists all 170 active ids exactly once, grouped by the nine shelf buttons in `products.json` order; the 2 held/inactive records are absent.
- exactSentenceCoverage: every quoted sentence is an exact substring of the product’s `description`, with its sentence number from a split after `.`, `!` or `?`; repeated sentences on distinct ids (Cal Poly chocolate, Stepladder cheese) have separate entries.
- partialEvidenceIsNotWholeSupport: Cambria place is shown against the location clause only; cultured butter, goat, creamery and similar clauses keep “no source found”.
- sourceIdentityAndPhotoLimits: the Munch results are not treated as Sean’s evidence; the October “owner confirmation remains in research file” and “development assumptions” wording is preserved; no original or generated image was inspected.
- scopeAndNoMutation: pure advice and metaphor are excluded, mixed factual/advice sentences are included (clauses only); blend-name places are not origin; organic prose is kept here while the badge rule is left to AV1052-14; no contact details or raw search dumps; only this Markdown file is added.
- Every research-log, maker and photo-note quote in this report was checked as a substring of its source record by the generator before writing; the PR body records the re-check run on the written file.

## Owner decisions needed

The owner decides each of these; nothing here is a proposed rewrite or an approval.

1. For each “no source found” clause in the lists above, keep the sentence, find a source (label, producer, owner confirmation), or reword it. The largest groups are the Cal Poly maker claims, Stepladder’s cheese, butter and honey, Mighty Cap products (including the dried mushrooms), Linn’s preserves and marmalades (fruit ingredient), Ocean Ranch “handmade organic”, and Fair Hills tea blends.
2. Sean’s Muesli Munch (“from San Luis Obispo”): decide whether the San Luis Obispo place in `makers.json` is enough, because the research result for that query belongs to unrelated Munch businesses.
3. Dream Girl Decaf, Zero non-alcoholic cider, Rye bread and Mortadella: decide what evidence is wanted for decaffeinated, non-alcoholic, rye and mortadella.
4. Maple Valley syrup (“from a Wisconsin cooperative”) and Joebella / Avocado Shack coffee: decide whether maker-level records are enough for a product-level sentence.
