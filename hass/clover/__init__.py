"""HASS-CLOVER-1 (prototype): Hass talks to the shop's Clover till for items and stock. Design: docs/hass/CLOVER.md.

Nothing in this package is wired into the running Hass service, reads a real token, or makes a network call in any test. Read-only client,
item mapper, SKU generator and draft builders; every Clover write is a draft the owner approves, and none is ever sent from here.
"""
