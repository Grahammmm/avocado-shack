"""AVB-12: hass/conversation.py split by pack. conversation.py is the dispatcher (store, approvals, the draft
flow and command routing in Conversation._command); each *_pack module holds the commands of one pack as a
mixin of Conversation, so two cards on two packs edit two files. shared, commands and wording are the
vocabulary they share. Every moved name is still importable from hass.conversation."""
