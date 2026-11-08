"""AV0007-03 (H05): the owner's words for argument ids in "Please provide" and "Give at least one of" questions.

One table. A field with no entry keeps its id. Only question prose is mapped; ops, records and the missing-id arrays
keep the real ids.
"""
from __future__ import annotations

FIELD_WORDS = {
    "imageAlt": "a few words saying what the photo shows",
    "displayBrand": "the brand shown on the card",
    "producerKey": "the maker",
    "rsvpEnabled": "whether guests can RSVP on the website",
    "sourceUrl": "the source link",
    "sourceName": "the source name",
    "meetingPoint": "the meeting place",
    "noCapacityLimit": "no guest limit",
    "trailId": "the route idea",
    "clearProducer": "remove the maker",
    "clearImageAlt": "remove the photo description",
    "clearUrl": "remove the website link",
    "url": "the website link",
    "image": "the photo",
    "photo": "the photo",
    "routeType": "the route type",
    "elevationLabel": "the elevation label",
    "streetAddress": "the street address",
    "name": "the name",
    "brand": "the brand",
    "category": "the category",
    "description": "the description",
    "place": "the place",
    "story": "the story",
    "title": "the title",
    "date": "the date",
    "time": "the time",
    "capacity": "the guest limit",
    "available": "availability",
    "meetingAddress": "the street address of the meeting place",
    "distance": "the distance",
    "difficulty": "how hard it is",
    "duration": "how long it takes",
    "meetTime": "when to meet",
    "walkTime": "when the walk starts",
    "returnTime": "when we get back",
    "invitation": "the invitation text",
    "bring": "what to bring",
    "accessNote": "the note about getting there",
}


def field_words(field: str) -> str:
    return FIELD_WORDS.get(field, field)


def field_list(fields) -> str:
    return ", ".join(field_words(f) for f in fields)
