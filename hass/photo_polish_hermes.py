"""HASS-IMAGE-1: the Hermes side of the photo polish. Run by the HERMES interpreter, never imported by Hass.

``hass/photo_polish.py`` starts this file as a child process of the Hermes Python (the one the ``hermes`` launcher
uses), so the image call goes through Hermes' own image plugin and Hermes' own sign-in. Hass never sees, reads or stores
a credential: this script does not read one either, it only asks the plugin for an edited picture.

Usage (Hermes python): photo_polish_hermes.py HERMES_ROOT MODEL INPUT OUTPUT PROMPT_FILE

* ``MODEL`` is ``<plugin>:<model id>``, for example ``openai-codex:gpt-image-2-high`` (Hermes' ChatGPT/Codex sign-in
  route to OpenAI gpt-image-2, quality high). The plugin edits INPUT (an image edit, not text-to-image).
* The edited picture is copied to OUTPUT. One JSON line goes to stdout:
  {"ok": true, "model": ..., "provider": ..., "pixel_size": "1024x1024", "request": <backend request id or null>}
  or {"ok": false, "code": "<short code>"}. No prompt, path, credential or error text is printed; a short code is all.
"""
import importlib
import json
import os
import shutil
import sys

CODES = {"auth_required": "auth", "missing_dependency": "dependency", "invalid_image_input": "input",
         "api_error": "api", "empty_response": "empty", "io_error": "io"}


def _say(**fields):
    sys.stdout.write(json.dumps(fields, sort_keys=True) + "\n")
    sys.stdout.flush()


def main(argv):
    if len(argv) != 6:
        _say(ok=False, code="usage")
        return 2
    root, model = argv[1], argv[2]
    src, out, prompt_file = (os.path.abspath(p) for p in argv[3:])
    plugin, _, tier = model.partition(":")
    if plugin != "openai-codex" or not tier:  # the only Hermes route with credentials today (G 2026-11-16)
        _say(ok=False, code="route")
        return 2
    sys.path.insert(0, root)
    os.chdir(root)
    sys._hermes_pin_default_home = True
    try:
        import hermes_bootstrap  # noqa: F401  (the same dependency bootstrap the hermes launcher runs)
        os.environ["OPENAI_IMAGE_MODEL"] = tier
        provider = importlib.import_module("plugins.image_gen.openai-codex").OpenAICodexImageGenProvider()
        with open(prompt_file, encoding="utf-8") as fh:
            prompt = fh.read()
        res = provider.generate(prompt, "square", image_url=src)
    except Exception:  # noqa: BLE001  (no traceback: it could carry paths)
        _say(ok=False, code="hermes")
        return 1
    if not isinstance(res, dict) or not res.get("success"):
        kind = res.get("error_type") if isinstance(res, dict) else None
        _say(ok=False, code=CODES.get(kind, "failed"))
        return 1
    if res.get("modality") != "image":  # an edit must have used the input photo
        _say(ok=False, code="not-edit")
        return 1
    try:
        shutil.copyfile(res["image"], out)
        os.unlink(res["image"])  # the Hermes cache keeps no copy of the product picture
    except (OSError, KeyError, TypeError):
        _say(ok=False, code="io")
        return 1
    extra = res.get("extra") or {}
    _say(ok=True, model=res.get("model"), provider=res.get("provider"), pixel_size=extra.get("pixel_size"),
         request=extra.get("imagegen_request_id"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
