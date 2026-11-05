# Catalog shelves: decisions for Michael (2026-11)

**For Michael to decide; nothing changed.** This report is words only. No product record, shelf, listing or site file was edited, and none of the messages below has been sent.

- Date: 2026-11-05
- Checked commit: `d61b69678d4855d2e0e32b61cd7da4440c14d4fd` (origin/main when this report was built)
- Source: [`hass/content/products.json`](../hass/content/products.json), the canonical catalog. Within a shelf, products are listed in the file's own order, which is the order the site shows them (`storefront-mockup/catalog-products.js` is generated from it).
- Shelf order: Fruit, Vegetables, Dairy & cheese, Eggs, Meat, Pantry, Drinks & coffee, Bread, Flowers, the order of the filter buttons in `hass/templates/index.html` (line 23) and `hass/content_model.py` `CATEGORIES`.
- Scope: the 170 products whose status is `active`. The 2 held products (photo-product-040, photo-product-133) are excluded and are not proposed for any action; they stay held.
- "Active" is a catalog status only. It does not mean in stock, confirmed packaging, or that the owner has approved the listing.
- Stored facts (shelf, name, brand, description) come from the file. Anything marked Judgment is a suggestion from the reviewer reading names and descriptions, not a record.

## Summary

- Possible shelf moves: 3 (section A).
- Possible overlaps between a general listing and specific ones: 6 groups, 6 general listings beside 22 named ones (section B).
- Every other active product: no concern found (section C).

| Shelf | Active products | Possible move | Possible overlap | No concern |
|---|---:|---:|---:|---:|
| Fruit | 13 | 0 | 0 | 13 |
| Vegetables | 52 | 2 | 22 | 28 |
| Dairy & cheese | 20 | 0 | 0 | 20 |
| Eggs | 1 | 0 | 0 | 1 |
| Meat | 3 | 0 | 0 | 3 |
| Pantry | 61 | 1 | 6 | 54 |
| Drinks & coffee | 15 | 0 | 0 | 15 |
| Bread | 4 | 0 | 0 | 4 |
| Flowers | 1 | 0 | 0 | 1 |
| **Total** | **170** | **3** | **28** | **139** |

## A. Products on a shelf a shopper might not look on

### A1. Cantaloupe

- Record: `photo-product-079`, [products.json:360](../hass/content/products.json#L360)
- Shelf now: Vegetables
- Suggested shelf: Fruit
- Why: Watermelon (photo-product-078) and the Honeydew-type melon (photo-product-080) are both on Fruit; a shopper looking for melon on Fruit would not find the cantaloupe. Judgment: this is a melon, so Fruit matches its two neighbours. Stored fact: the description says "Cut through the netted rind and follow the aroma. Serve chilled", i.e. it is eaten as fruit.
- Message Michael could send Hass: "Move the cantaloupe to the fruit shelf."

### A2. Montaña de Oro Sea Salt tortilla chips

- Record: `photo-product-018`, [products.json:151](../hass/content/products.json#L151)
- Shelf now: Vegetables
- Suggested shelf: Pantry
- Why: A bag of packaged tortilla chips is not fresh produce, so a shopper browsing Vegetables would not expect it. Judgment: Pantry is where the other packaged snacks and sauces sit (for example Sean's muesli munch, Trail mix, the hot sauces). Stored fact: the brand is Taco Works and the description reads "Open the bag when the guacamole is ready".
- Message Michael could send Hass: "Move the Taco Works Montaña de Oro Sea Salt tortilla chips to the pantry shelf."

### A3. Avocado Shack (Hands)

- Record: `photo-product-093`, [products.json:1306](../hass/content/products.json#L1306)
- Shelf now: Pantry
- Suggested shelf: Drinks & coffee
- Why: The description calls it coffee ("Avocado Shack coffee for the kitchen counter. Grind it fresh, make a cup"), and the seven other Joebella / Avocado Shack blends are on Drinks & coffee: Albino Coast Redwood Blend, Cone Peak Blend, Dream Girl Decaf, Peace Be With You Blend, Avocado Shack Blend (Hut), Cass Hill Blend and Cambria Blend. Same brand line, so a shopper would look for it there. Stored fact: its shelf is Pantry.
- Message Michael could send Hass: "Move Avocado Shack (Hands) coffee to the Drinks & coffee shelf."

If Michael prefers to keep any of these where they are, no message is needed.

## B. General listings beside specific ones

Each general listing below sits on the same shelf as the specific listings named with it. Overlap is a question, not proof: the general listing may be intentional (a mixed bag, or kinds with no listing of their own). For each group, Michael is asked: **is the general listing a different item from the named ones?** If it is, nothing to do. If it is not, the message to Hass is the hide wording. Hiding is reversible (a hidden product can be restored), and the named listings stay as they are.

### B1. Potatoes

- General listing: Potatoes, `photo-product-067`, [products.json:239](../hass/content/products.json#L239)
- Specific listings, same shelf (Vegetables):
  - Gold potatoes, `photo-product-145`, [products.json:434](../hass/content/products.json#L434)
  - Red potatoes, `photo-product-146`, [products.json:445](../hass/content/products.json#L445)
  - Purple potatoes, `photo-product-147`, [products.json:456](../hass/content/products.json#L456)
- Why it may be intentional: The general listing may be a mixed or unsorted bag, or a stall that sells whichever potatoes are in; the three colours may be the only potatoes now.
- Question for Michael: is "Potatoes" a different item from these 3? If not:
- Message Michael could send Hass: "Hide the Potatoes listing."

### B2. Lettuce

- General listing: Lettuce, `photo-product-068`, [products.json:250](../hass/content/products.json#L250)
- Specific listings, same shelf (Vegetables):
  - Romaine lettuce, `photo-product-062`, [products.json:184](../hass/content/products.json#L184)
- Why it may be intentional: The general listing may cover other lettuces (butter, green leaf) that have no listing of their own; Romaine is only one kind.
- Question for Michael: is "Lettuce" a different item from these 1? If not:
- Message Michael could send Hass: "Hide the Lettuce listing."

### B3. Mushrooms

- General listing: Mushrooms, `photo-product-071`, [products.json:283](../hass/content/products.json#L283)
- Specific listings, same shelf (Vegetables):
  - Lion’s mane mushrooms, `photo-product-150`, [products.json:489](../hass/content/products.json#L489)
  - King oyster mushrooms, `photo-product-151`, [products.json:500](../hass/content/products.json#L500)
  - Shiitake mushrooms, `photo-product-152`, [products.json:511](../hass/content/products.json#L511)
  - Maitake mushrooms, `photo-product-153`, [products.json:522](../hass/content/products.json#L522)
  - Chanterelle mushrooms, `photo-product-154`, [products.json:533](../hass/content/products.json#L533)
  - Lobster mushrooms, `photo-product-155`, [products.json:544](../hass/content/products.json#L544)
  - Crimini mushrooms, `photo-product-156`, [products.json:555](../hass/content/products.json#L555)
- Why it may be intentional: The general listing may be a mixed or whatever-is-picked tray; seven named kinds are listed beside it. These are fresh mushrooms: do not confuse them with the dried ones on Pantry or with Mushroom Umami Sauce.
- Question for Michael: is "Mushrooms" a different item from these 7? If not:
- Message Michael could send Hass: "Hide the Mushrooms listing."

### B4. Peppers

- General listing: Peppers, `photo-product-076`, [products.json:338](../hass/content/products.json#L338)
- Specific listings, same shelf (Vegetables):
  - Sweet peppers, `photo-product-163`, [products.json:632](../hass/content/products.json#L632)
  - Red bell peppers, `photo-product-164`, [products.json:643](../hass/content/products.json#L643)
  - Poblano peppers, `photo-product-165`, [products.json:654](../hass/content/products.json#L654)
- Why it may be intentional: The general listing may cover peppers with no listing of their own (Jalapeños have one, but other kinds do not); the three named kinds may not be all of it.
- Question for Michael: is "Peppers" a different item from these 3? If not:
- Message Michael could send Hass: "Hide the Peppers listing."

### B5. Tomatoes

- General listing: Tomatoes, `photo-product-077`, [products.json:349](../hass/content/products.json#L349)
- Specific listings, same shelf (Vegetables):
  - San Marzano tomatoes, `photo-product-168`, [products.json:687](../hass/content/products.json#L687)
  - Cherry tomatoes, `photo-product-169`, [products.json:698](../hass/content/products.json#L698)
  - Sun Gold tomatoes, `photo-product-170`, [products.json:709](../hass/content/products.json#L709)
- Why it may be intentional: The general listing may be slicing or heirloom tomatoes, which none of the three named kinds covers.
- Question for Michael: is "Tomatoes" a different item from these 3? If not:
- Message Michael could send Hass: "Hide the Tomatoes listing."

### B6. Dried mushrooms

- General listing: Dried mushrooms, `photo-product-044`, [products.json:1163](../hass/content/products.json#L1163)
- Specific listings, same shelf (Pantry):
  - Dried lion’s mane mushrooms, `photo-product-046`, [products.json:1185](../hass/content/products.json#L1185)
  - Dried maitake mushrooms, `photo-product-047`, [products.json:1196](../hass/content/products.json#L1196)
  - Dried morels, `photo-product-134`, [products.json:1501](../hass/content/products.json#L1501)
  - Dried shiitake, `photo-product-135`, [products.json:1512](../hass/content/products.json#L1512)
  - Dried king oyster mushrooms, `photo-product-136`, [products.json:1523](../hass/content/products.json#L1523)
- Why it may be intentional: The general listing may be a mixed bag of dried mushrooms. The five named kinds are all dried and Pantry; Mushroom Umami Sauce (photo-product-137) is a sauce and is not part of this group.
- Question for Michael: is "Dried mushrooms" a different item from these 5? If not:
- Message Michael could send Hass: "Hide the Dried mushrooms listing."

## C. Every active product, by shelf in site order

Each of the 170 active products appears exactly once below. "Result" is one of: no concern, possible move (section A), possible overlap (section B). Other candidates considered and not raised: Loose carrots / Bunched carrots (two forms, both named); Wild Arugula (Jayleaf) / Arugula microgreens (different products); Strawberry preserves (Linn's) / Cal Poly strawberry jam (different makers and products); Guacamole and Garlic pesto (Stardust Grove) on Pantry, which is a judgment call about chilled goods and is left to Michael, with no change suggested.

### Fruit (13)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-001 | Hass avocado | Fruit | no concern |
| 2 | photo-product-016 | Oranges | Fruit | no concern |
| 3 | photo-product-017 | Lemons | Fruit | no concern |
| 4 | photo-product-056 | Strawberries | Fruit | no concern |
| 5 | photo-product-057 | Raspberries | Fruit | no concern |
| 6 | photo-product-058 | Blueberries | Fruit | no concern |
| 7 | photo-product-059 | Golden raspberries | Fruit | no concern |
| 8 | photo-product-078 | Watermelon | Fruit | no concern |
| 9 | photo-product-080 | Honeydew-type melon | Fruit | no concern |
| 10 | photo-product-081 | Keitt mango | Fruit | no concern |
| 11 | photo-product-096 | Passion fruit | Fruit | no concern |
| 12 | photo-product-097 | Figs | Fruit | no concern |
| 13 | photo-product-098 | Blackberries | Fruit | no concern |

### Vegetables (52)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-018 | Montaña de Oro Sea Salt tortilla chips | Vegetables | possible move: Pantry, see A2 |
| 2 | photo-product-060 | Fennel | Vegetables | no concern |
| 3 | photo-product-061 | Broccoli | Vegetables | no concern |
| 4 | photo-product-062 | Romaine lettuce | Vegetables | possible overlap (specific), see B2 |
| 5 | photo-product-063 | Bok choy | Vegetables | no concern |
| 6 | photo-product-064 | Leeks | Vegetables | no concern |
| 7 | photo-product-065 | Celery | Vegetables | no concern |
| 8 | photo-product-066 | Bunched carrots | Vegetables | no concern |
| 9 | photo-product-067 | Potatoes | Vegetables | possible overlap (general), see B1 |
| 10 | photo-product-068 | Lettuce | Vegetables | possible overlap (general), see B2 |
| 11 | photo-product-069 | Spring Greens | Vegetables | no concern |
| 12 | photo-product-070 | Wild Arugula | Vegetables | no concern |
| 13 | photo-product-071 | Mushrooms | Vegetables | possible overlap (general), see B3 |
| 14 | photo-product-072 | Sunflower microgreens | Vegetables | no concern |
| 15 | photo-product-073 | Ginger | Vegetables | no concern |
| 16 | photo-product-074 | Turmeric | Vegetables | no concern |
| 17 | photo-product-075 | Eggplant | Vegetables | no concern |
| 18 | photo-product-076 | Peppers | Vegetables | possible overlap (general), see B4 |
| 19 | photo-product-077 | Tomatoes | Vegetables | possible overlap (general), see B5 |
| 20 | photo-product-079 | Cantaloupe | Vegetables | possible move: Fruit, see A1 |
| 21 | photo-product-099 | Garlic | Vegetables | no concern |
| 22 | photo-product-100 | Shallots | Vegetables | no concern |
| 23 | photo-product-101 | Yellow onions | Vegetables | no concern |
| 24 | photo-product-102 | Red onions | Vegetables | no concern |
| 25 | photo-product-103 | Radicchio | Vegetables | no concern |
| 26 | photo-product-104 | Purple daikon | Vegetables | no concern |
| 27 | photo-product-145 | Gold potatoes | Vegetables | possible overlap (specific), see B1 |
| 28 | photo-product-146 | Red potatoes | Vegetables | possible overlap (specific), see B1 |
| 29 | photo-product-147 | Purple potatoes | Vegetables | possible overlap (specific), see B1 |
| 30 | photo-product-148 | Loose carrots | Vegetables | no concern |
| 31 | photo-product-149 | Green cabbage | Vegetables | no concern |
| 32 | photo-product-150 | Lion’s mane mushrooms | Vegetables | possible overlap (specific), see B3 |
| 33 | photo-product-151 | King oyster mushrooms | Vegetables | possible overlap (specific), see B3 |
| 34 | photo-product-152 | Shiitake mushrooms | Vegetables | possible overlap (specific), see B3 |
| 35 | photo-product-153 | Maitake mushrooms | Vegetables | possible overlap (specific), see B3 |
| 36 | photo-product-154 | Chanterelle mushrooms | Vegetables | possible overlap (specific), see B3 |
| 37 | photo-product-155 | Lobster mushrooms | Vegetables | possible overlap (specific), see B3 |
| 38 | photo-product-156 | Crimini mushrooms | Vegetables | possible overlap (specific), see B3 |
| 39 | photo-product-157 | Cilantro microgreens | Vegetables | no concern |
| 40 | photo-product-158 | Radish Mix microgreens | Vegetables | no concern |
| 41 | photo-product-159 | Arugula microgreens | Vegetables | no concern |
| 42 | photo-product-160 | Broccoli microgreens | Vegetables | no concern |
| 43 | photo-product-161 | Horseradish | Vegetables | no concern |
| 44 | photo-product-162 | Jalapeños | Vegetables | no concern |
| 45 | photo-product-163 | Sweet peppers | Vegetables | possible overlap (specific), see B4 |
| 46 | photo-product-164 | Red bell peppers | Vegetables | possible overlap (specific), see B4 |
| 47 | photo-product-165 | Poblano peppers | Vegetables | possible overlap (specific), see B4 |
| 48 | photo-product-166 | Zucchini | Vegetables | no concern |
| 49 | photo-product-167 | Green onions | Vegetables | no concern |
| 50 | photo-product-168 | San Marzano tomatoes | Vegetables | possible overlap (specific), see B5 |
| 51 | photo-product-169 | Cherry tomatoes | Vegetables | possible overlap (specific), see B5 |
| 52 | photo-product-170 | Sun Gold tomatoes | Vegetables | possible overlap (specific), see B5 |

### Dairy & cheese (20)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-025 | Straus half-and-half | Dairy & cheese | no concern |
| 2 | photo-product-026 | Straus heavy whipping cream | Dairy & cheese | no concern |
| 3 | photo-product-027 | Organic whole milk | Dairy & cheese | no concern |
| 4 | photo-product-028 | Straus butter | Dairy & cheese | no concern |
| 5 | photo-product-029 | Ragged Point cheese | Dairy & cheese | no concern |
| 6 | photo-product-030 | Stepladder cultured butter | Dairy & cheese | no concern |
| 7 | photo-product-033 | Stepladder Rocky Butte cheese | Dairy & cheese | no concern |
| 8 | photo-product-034 | Stepladder Bixby cheese | Dairy & cheese | no concern |
| 9 | photo-product-035 | Chèvre | Dairy & cheese | no concern |
| 10 | photo-product-037 | Cal Poly chipotle cheddar | Dairy & cheese | no concern |
| 11 | photo-product-038 | Cal Poly white cheddar | Dairy & cheese | no concern |
| 12 | photo-product-039 | Cal Poly Highland cheddar | Dairy & cheese | no concern |
| 13 | photo-product-125 | Whole Milk Plain European Style yogurt | Dairy & cheese | no concern |
| 14 | photo-product-126 | Greek Whole Milk Plain yogurt | Dairy & cheese | no concern |
| 15 | photo-product-127 | Sour cream | Dairy & cheese | no concern |
| 16 | photo-product-128 | Big Sur cheese | Dairy & cheese | no concern |
| 17 | photo-product-129 | Marinated Fromage Blanc | Dairy & cheese | no concern |
| 18 | photo-product-130 | Gouda | Dairy & cheese | no concern |
| 19 | photo-product-131 | Hatch Chile Sierra Jack | Dairy & cheese | no concern |
| 20 | photo-product-132 | Habanero Sierra Jack | Dairy & cheese | no concern |

### Eggs (1)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-024 | Cal Poly eggs | Eggs | no concern |

### Meat (3)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-021 | Alle-Pia Calabrese salamini | Meat | no concern |
| 2 | photo-product-022 | Alle-Pia guanciale | Meat | no concern |
| 3 | photo-product-023 | Alle-Pia mortadella | Meat | no concern |

### Pantry (61)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-002 | Linn's triple berry preserves | Pantry | no concern |
| 2 | photo-product-003 | Linn's blueberry preserves | Pantry | no concern |
| 3 | photo-product-004 | Linn's boysenberry preserves | Pantry | no concern |
| 4 | photo-product-005 | Linn's orange marmalade | Pantry | no concern |
| 5 | photo-product-008 | Cal Poly strawberry jam | Pantry | no concern |
| 6 | photo-product-009 | Cal Poly raspberry jam | Pantry | no concern |
| 7 | photo-product-010 | Cal Poly blackberry jam | Pantry | no concern |
| 8 | photo-product-011 | Sweet Hickory BBQ sauce | Pantry | no concern |
| 9 | photo-product-012 | Cal Poly chocolate | Pantry | no concern |
| 10 | photo-product-013 | Original hot sauce | Pantry | no concern |
| 11 | photo-product-031 | Guacamole | Pantry | no concern |
| 12 | photo-product-032 | Garlic pesto | Pantry | no concern |
| 13 | photo-product-041 | Stepladder avocado blossom honey | Pantry | no concern |
| 14 | photo-product-042 | Big Sur Honey Company honey | Pantry | no concern |
| 15 | photo-product-043 | Sunshine Estate olive oil | Pantry | no concern |
| 16 | photo-product-044 | Dried mushrooms | Pantry | possible overlap (general), see B6 |
| 17 | photo-product-045 | Sunshine Olive Spanish Oaks Picual olive oil | Pantry | no concern |
| 18 | photo-product-046 | Dried lion’s mane mushrooms | Pantry | possible overlap (specific), see B6 |
| 19 | photo-product-047 | Dried maitake mushrooms | Pantry | possible overlap (specific), see B6 |
| 20 | photo-product-052 | Maple Valley dark and robust maple syrup | Pantry | no concern |
| 21 | photo-product-053 | Sean's muesli munch | Pantry | no concern |
| 22 | photo-product-054 | Massa Organics brown rice | Pantry | no concern |
| 23 | photo-product-055 | Cashews | Pantry | no concern |
| 24 | photo-product-082 | Artisan short-cut pasta | Pantry | no concern |
| 25 | photo-product-088 | Cranberry Orange granola | Pantry | no concern |
| 26 | photo-product-089 | Oaxacan Chocolate granola | Pantry | no concern |
| 27 | photo-product-090 | Lemon Blueberry granola | Pantry | no concern |
| 28 | photo-product-091 | Turmeric Goji Berry granola | Pantry | no concern |
| 29 | photo-product-093 | Avocado Shack (Hands) | Pantry | possible move: Drinks & coffee, see A3 |
| 30 | photo-product-105 | Sunshine Peach preserves | Pantry | no concern |
| 31 | photo-product-106 | Strawberry preserves | Pantry | no concern |
| 32 | photo-product-107 | California Apricot preserves | Pantry | no concern |
| 33 | photo-product-108 | Blood Orange marmalade | Pantry | no concern |
| 34 | photo-product-109 | Peppermint Crunch chocolate | Pantry | no concern |
| 35 | photo-product-110 | Cookies and Cream chocolate | Pantry | no concern |
| 36 | photo-product-111 | Zesty Orange chocolate | Pantry | no concern |
| 37 | photo-product-112 | Dark chocolate | Pantry | no concern |
| 38 | photo-product-113 | Milk chocolate | Pantry | no concern |
| 39 | photo-product-114 | Lemon Bar white chocolate | Pantry | no concern |
| 40 | photo-product-115 | Habanero chocolate | Pantry | no concern |
| 41 | photo-product-116 | S’mores chocolate | Pantry | no concern |
| 42 | photo-product-117 | Lemon Lavender white chocolate | Pantry | no concern |
| 43 | photo-product-118 | Birthday Cake chocolate | Pantry | no concern |
| 44 | photo-product-119 | Mustang Kick BBQ sauce | Pantry | no concern |
| 45 | photo-product-120 | Carrot Habanero hot sauce | Pantry | no concern |
| 46 | photo-product-121 | Green hot sauce | Pantry | no concern |
| 47 | photo-product-134 | Dried morels | Pantry | possible overlap (specific), see B6 |
| 48 | photo-product-135 | Dried shiitake | Pantry | possible overlap (specific), see B6 |
| 49 | photo-product-136 | Dried king oyster mushrooms | Pantry | possible overlap (specific), see B6 |
| 50 | photo-product-137 | Mushroom Umami Sauce | Pantry | no concern |
| 51 | photo-product-138 | Crimson lentils | Pantry | no concern |
| 52 | photo-product-139 | Red beans | Pantry | no concern |
| 53 | photo-product-140 | Black beans | Pantry | no concern |
| 54 | photo-product-141 | Chickpeas | Pantry | no concern |
| 55 | photo-product-142 | Almonds | Pantry | no concern |
| 56 | photo-product-143 | Pistachios | Pantry | no concern |
| 57 | photo-product-144 | Trail mix | Pantry | no concern |
| 58 | photo-product-171 | Radiatori pasta | Pantry | no concern |
| 59 | photo-product-172 | Rigatoni pasta | Pantry | no concern |
| 60 | photo-product-173 | Casarecce pasta | Pantry | no concern |
| 61 | photo-product-174 | Conchiglie pasta | Pantry | no concern |

### Drinks & coffee (15)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-007 | Fair Hills Farm apple juice | Drinks & coffee | no concern |
| 2 | photo-product-014 | Zero non-alcoholic cider | Drinks & coffee | no concern |
| 3 | photo-product-019 | Organic beet juice | Drinks & coffee | no concern |
| 4 | photo-product-048 | Fair Hills Farm chamomile tea | Drinks & coffee | no concern |
| 5 | photo-product-049 | Fair Hills Farm black tea | Drinks & coffee | no concern |
| 6 | photo-product-050 | Fair Hills Farm cinnamon black tea | Drinks & coffee | no concern |
| 7 | photo-product-051 | Ginger black tea | Drinks & coffee | no concern |
| 8 | photo-product-083 | Albino Coast Redwood Blend | Drinks & coffee | no concern |
| 9 | photo-product-084 | Cone Peak Blend | Drinks & coffee | no concern |
| 10 | photo-product-085 | Dream Girl Decaf | Drinks & coffee | no concern |
| 11 | photo-product-086 | Peace Be With You Blend | Drinks & coffee | no concern |
| 12 | photo-product-087 | Packer’s Blend coffee bags | Drinks & coffee | no concern |
| 13 | photo-product-092 | Avocado Shack Blend (Hut) | Drinks & coffee | no concern |
| 14 | photo-product-094 | Cass Hill Blend | Drinks & coffee | no concern |
| 15 | photo-product-095 | Cambria Blend | Drinks & coffee | no concern |

### Bread (4)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-015 | Brian's sourdough bread | Bread | no concern |
| 2 | photo-product-122 | Rye bread | Bread | no concern |
| 3 | photo-product-123 | Rosemary Sourdough with Olive Oil | Bread | no concern |
| 4 | photo-product-124 | Cracked Wheat Sourdough | Bread | no concern |

### Flowers (1)

| # | ID | Name | Shelf now | Result |
|---:|---|---|---|---|
| 1 | photo-product-006 | Mixed flower bouquet | Flowers | no concern |

Total: 170 active products checked (Fruit 13 + Vegetables 52 + Dairy & cheese 20 + Eggs 1 + Meat 3 + Pantry 61 + Drinks & coffee 15 + Bread 4 + Flowers 1).

## Not done

No record was changed, no shelf moved, no listing hidden, and no message sent. Michael decides; if he wants any change he sends the plain messages above to Hass. If the catalog changes before then, re-check each item against the file first.
