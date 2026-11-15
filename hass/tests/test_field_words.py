"""AV0007-03 (H05): FIELD_WORDS is the one table of owner words for argument ids.
Run: python3 -B -m unittest hass.tests.test_field_words -v
"""

import copy
import unittest

from hass.field_words import FIELD_WORDS, field_list, field_words

PINNED = {
    "imageAlt": "a few words saying what the photo shows", "displayBrand": "the brand shown on the card",
    "producerKey": "the maker", "rsvpEnabled": "whether guests can RSVP on the website",
    "sourceUrl": "the source link", "sourceName": "the source name", "meetingPoint": "the meeting place",
    "noCapacityLimit": "no guest limit", "trailId": "the route idea", "clearProducer": "remove the maker",
    "clearImageAlt": "remove the photo description", "clearUrl": "remove the website link",
    "clearStory": "remove the story",  # AV0222-10
    "url": "the website link", "image": "the photo", "photo": "the photo", "routeType": "the route type",
    "elevationLabel": "the elevation label", "streetAddress": "the street address", "name": "the name",
    "brand": "the brand", "category": "the category", "description": "the description", "place": "the place",
    "story": "the story", "title": "the title", "date": "the date", "time": "the time",
    "capacity": "the guest limit", "available": "availability",
    "meetingAddress": "the street address of the meeting place", "distance": "the distance", "difficulty": "how hard it is",
    "duration": "how long it takes", "meetTime": "when to meet", "walkTime": "when the walk starts",
    "returnTime": "when we get back", "invitation": "the invitation text", "bring": "what to bring",
    "accessNote": "the note about getting there",
    "id": "which one you mean", "changeId": "the change to undo",
}


class FieldWordsTests(unittest.TestCase):
    def test_known_target_ids_have_plain_display_words(self):
        self.assertEqual(FIELD_WORDS, PINNED)
        self.assertEqual(FIELD_WORDS["id"], "which one you mean")
        self.assertEqual(FIELD_WORDS["changeId"], "the change to undo")
        self.assertEqual(field_list(["id"]), "which one you mean")
        self.assertEqual(field_list(["changeId"]), "the change to undo")
        self.assertEqual(field_list(["id", "imageAlt", "id"]),
                         "which one you mean, a few words saying what the photo shows, which one you mean")

    def test_unknown_fallback_and_ordinary_fields_unchanged(self):
        before = copy.deepcopy(FIELD_WORDS)
        self.assertEqual(field_words("terrain"), "terrain")  # no entry: the id itself
        self.assertEqual(field_words("changeid"), "changeid")  # only the exact known names are mapped
        self.assertEqual(field_words("sourceUrl"), "the source link")
        self.assertEqual(field_words(""), "")
        self.assertEqual(field_list(["terrain", "imageAlt", "producerKey", "terrain"]),
                         "terrain, a few words saying what the photo shows, the maker, terrain")  # order and repeats kept
        self.assertEqual(field_list([]), "")
        fields = ["time", "date"]
        field_list(fields)
        self.assertEqual((fields, FIELD_WORDS), (["time", "date"], before))  # nothing mutated


if __name__ == "__main__":
    unittest.main()
