# What happens when another product photo arrives?

These are offline observations for the same owner in the same chat with the new-product pipeline on. The tests exercise Hass's message routing, listing decisions, and approval checks with synthetic photo reads, cards, and delivery confirmations. They do not send or publish anything.

| When the photo arrives | What Hass does today | Test |
| --- | --- | --- |
| **Waiting for a price.** A bare photo shows a different product. | Hass keeps the same job but replaces its photo. It asks for the selling price and unit again. Once the owner answers, the card is for the second product; the first product does not get its own card. | `test_c1_while_asking` |
| **A card has been delivered.** A bare photo shows a different product. | Hass takes it as an edit to the same job and immediately makes the first card unapprovable. It asks “I didn't catch that change. What should it say?” rather than starting a second listing or sending a new card. A yes to the original code gets “The card isn't ready to approve yet; use the code on it when it arrives.” | `test_c2_while_card_out` |
| **An edited card is being built.** A bare photo shows a different product. | Hass keeps the same job and replaces its photo. The in-progress card is set aside even if the build finishes successfully. Hass sends the same edit question, not the in-progress card. | `test_c3_while_building` |
| **A new shot of the same product.** A card has already been delivered. | A bare retake replaces the photo in the job, invalidates the original card, and gets the edit question. In the test, resending the retake with a price change produces a new card for the same listing with the replacement picture. Only the new card's code works; the old code gets “That card was replaced.” | `test_c4_same_product_again` |
| **Two different products in one message.** No job is open. | Both photos go into one identification request, in message order. The first supplies the listing picture, and Hass sends one card, not one per photo. | `test_c5_two_products_one_message` |

## Options for the pilot (no decision taken)

| Option | Upside | Downside |
| --- | --- | --- |
| Always treat new photos as part of the open job. | A retake can be sent without a separate command. | A different product can displace work in progress or invalidate a card the owner meant to approve. |
| Ask whether to replace the photo or save it for the next listing. | Keeps the current card intact until the owner says what the new photo is for. | Adds a turn and requires keeping the photo while waiting for a choice. |
| Require “replace photo” for the open job; queue other photos for later. | The owner can send products back to back without changing the open card. | Requires an explicit cue for retakes and clear feedback about what is queued. |
