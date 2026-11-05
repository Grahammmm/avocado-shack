"""AV1052-10 tests: a photo caption the reader could not read leaves the photo's needs-details draft open;
status says to reply to that draft (resending the photo is a duplicate and reads nothing), and the reply is read.

Run: python3 -m unittest hass.tests.test_photo_caption_reader_failed -v
"""

import unittest

from hass.tests import test_photo_draft as base
from hass.tests.test_photo_draft import ANSWER, PhotoInterpreter


class FailingReader(PhotoInterpreter):
    def __init__(self):
        super().__init__()
        self.last_error, self.down = None, True

    def interpret(self, text, pending, **kw):
        if self.down:
            self.texts.append(text)
            self.last_error = "http-503"
            return {"unsupported": "I could not work that out right now, so nothing was drafted."}
        self.last_error = None
        return super().interpret(text, pending, **kw)


class PhotoCaptionReaderFailedTests(unittest.TestCase):
    open, say, replies, drafts = (base.PhotoDraftTests.open, base.PhotoDraftTests.say, base.PhotoDraftTests.replies,
                                  base.PhotoDraftTests.drafts)

    def setUp(self):
        base.PhotoDraftTests.setUp(self)
        self.interp = FailingReader()
        self.conv = self.open()

    def status(self):
        self.replies()
        self.assertEqual(self.say("status"), "status")
        return self.replies()[0].splitlines()

    def test_failed_caption_status_names_the_draft_and_retry_reads_the_reply(self):
        self.assertEqual(self.say(ANSWER, attachments=1), "reader-failed")
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "needs-details")
        code = draft["code"]
        line = [x for x in self.status() if x.startswith("Last request not read")]
        self.assertEqual(len(line), 1, line)
        self.assertIn(f"draft {code}", line[0])
        self.assertIn("reply to it with the product and description", line[0])
        self.assertNotIn("send it again", line[0])
        # resending the same photo is only a duplicate: no second draft, the caption is still unread
        calls = len(self.interp.texts)
        self.assertEqual(self.say(ANSWER, attachments=1), "photo-duplicate")
        self.assertEqual((len(self.drafts()), len(self.interp.texts)), (1, calls))
        # the recovery the status line gives: reply to the open draft once the reader works
        self.interp.down = False
        self.assertEqual(self.say(ANSWER), "proposed")
        self.assertEqual([d["state"] for d in self.drafts()].count("needs-details"), 0)
        self.assertFalse([x for x in self.status() if x.startswith("Last request not read")])

    def test_failed_text_request_still_says_send_it_again(self):
        self.assertEqual(self.say("nonsense"), "reader-failed")
        [line] = [x for x in self.status() if x.startswith("Last request not read")]
        self.assertTrue(line.endswith("send it again"), line)


if __name__ == "__main__":
    unittest.main()
