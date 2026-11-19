"""Description metadata inside skipped containers is not page content (synthetic markup only)."""
import unittest

from hass import maker_site as ms

FACT = "Harbor Lane makes small-batch fruit jam in Morro Bay."


def meta(kind="name", value="description", text="Hidden claim", close=""):
    return f'<meta {kind}="{value}" content="{text}"{close}>'


class HiddenMeta(unittest.TestCase):
    def test_hidden_description_meta_is_not_extracted(self):
        for tag in ("template", "nav", "footer", "form", "aside", "button"):
            for kind, value in (("name", "description"), ("property", "og:description")):
                with self.subTest(tag=tag, kind=kind):
                    markup = f"<{tag}>{meta(kind, value)}</{tag}><p>Visible paragraph.</p>"
                    self.assertEqual(ms.extract(markup), ["Visible paragraph."])

    def test_nested_skip_and_self_closing_meta_do_not_leak(self):
        markup = (f"<nav><div><template>{meta(close=' /')}</template>{meta('property', 'og:description', 'Second')}"
                  f"</div>{meta(text='Third', close='/')}</nav><p>Visible paragraph.</p>")
        self.assertEqual(ms.extract(markup), ["Visible paragraph."])
        after = f"<nav><template></template></nav>{meta(text='Visible description')}<p>Visible paragraph.</p>"
        self.assertEqual(ms.extract(after), ["Visible description", "Visible paragraph."])

    def test_visible_metadata_and_paragraph_order_are_preserved(self):
        markup = f"<html><head>{meta(text='Visible description')}</head><body><p>Visible paragraph.</p></body></html>"
        self.assertEqual(ms.extract(markup), ["Visible description", "Visible paragraph."])

    def test_hidden_metadata_cannot_supply_a_maker_story(self):
        hidden = ms.extract(f"<template>{meta(text=FACT)}</template>")
        self.assertEqual(hidden, [])
        self.assertIsNone(ms.draft_story("Harbor Lane", {"blocks": hidden}, town="Morro Bay"))
        visible = ms.extract(meta(text=FACT))
        self.assertEqual(visible, [FACT])
        self.assertIsNotNone(ms.draft_story("Harbor Lane", {"blocks": visible}, town="Morro Bay"))


if __name__ == "__main__":
    unittest.main()
