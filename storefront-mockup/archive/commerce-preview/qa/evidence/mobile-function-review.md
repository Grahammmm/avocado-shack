# Mobile interaction review

Tested Chromium touch emulation at widths 320, 390, and 430px. Main flow used 844px height; long-dialog flow used 700px height.

## Passed

- No document horizontal overflow at all three widths.
- Category buttons wrap and remain fully available; Fruit changes count to 13 products and reports aria-pressed=true.
- Native producer select filters results; first producer combined with Fruit yields one result. Search and producer controls have enclosing labels.
- Product dialog initially focuses Close. Escape closes and restores focus to the opening product image button.
- Long-dialog keyboard Tab remains inside the dialog.
- Adding an avocado, increasing quantity to two, selecting delivery, entering an address, and reviewing shows 2 × Hass avocado and $10 total ($4 items + $6 delivery).
- Keep shopping closes the review. No uncaught browser errors in these flows.
- Scrolling to the catalog sentinel loads all 170 items. Categories currently wrap over four rows at 320px and three at 390/430px; the filter container has no horizontal overflow.

## Fixes

1. **Keep Close visible while dialog content scrolls.** At 320 × 700, Small Vegetable Box has 896px content within a 616px dialog. After scrolling to the bottom, Close spans y=-230 to -183; at 390/430px it spans y=-118 to -71. The touch close action disappears. Place Close in a sticky header outside the scrollable content or use a fixed dialog header and a separately scrolling content region. Preserve native Escape behavior.
2. **Give every dialog an accessible name.** The dialog has neither aria-label nor aria-labelledby. Assign an ID to the currently rendered heading and set dialog aria-labelledby to that ID in show(). Native dialog modal/focus behavior otherwise works in this test.
3. **Increase compact touch targets.** Header navigation links are 19.2px tall; footer Hours & location is 19.2px and Privacy & ordering is 21.2px. Basket is 39.2px high, Close is 28px wide, and mobile quantity +/- is 32px wide × 44px high. Use at least 44px minimum width/height with spacing for comfortable touch use. Main filter and product action targets already have 44px minimum height.

## Evidence and limits

Measurements and flow results are in mobile-function-qa.json and mobile-function-long-qa.json. Reproduction scripts are mobile-function-qa.cjs and mobile-function-long-qa.cjs. No source edits made. Browser emulation does not establish actual iOS Safari/Android behavior, virtual keyboard behavior, or screen-reader announcements; dialog naming issue is established directly by DOM inspection.
