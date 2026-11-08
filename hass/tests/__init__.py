"""HASS-VOICE-1: every hass test runs with the voice check strict: an owner message that breaks a voice rule raises
(hass/voice.py) instead of being swapped for the safe line, so a bad template fails the build."""
import os

os.environ["HASS_VOICE_STRICT"] = "1"
