# Pillow on the Hass host (operator steps)

Pillow is the image library the house-style picture code uses (resize, centre on the ivory background,
save as JPEG). CI installs it per job at the version in `PILLOW_VERSION` in `.github/workflows/check.yml`
(currently **12.0.0**). The host must run the same version, so a picture that passes in CI is the same
picture Hass makes. This file is an instruction: the card that wrote it did not run anything on the host.

## Install (operator, on AgentOrange)

Hass runs from the runtime worktree with the system `python3`. Install into a folder that only Hass
reads, not into the system Python:

1. `python3 -m venv ~/.local/share/hass/venv` (skip if it exists)
2. `~/.local/share/hass/venv/bin/pip install --only-binary=:all: "Pillow==12.0.0"`
3. Make the Hass services use that Python. systemd does not expand `~` in `ExecStart`; use `%h`
   (the user's home) or an absolute path. The receiver and worker units currently start
   `/usr/bin/python3 -B ...`. In the installed user units, change only the interpreter and keep every
   other argument as it is:

   `ExecStart=%h/.local/share/hass/venv/bin/python3 -B %h/.local/share/hass/runtime/hass/host.py serve ...`
   (receiver) and the same interpreter in `hass-worker.service` (`... host.py work ...`).

   The installed copies are in `~/.config/systemd/user/`; the templates in `deploy/hass` are what they
   were installed from, so make the same one-word interpreter change in the template in a later
   reviewed pull request or the next install will undo it. Apply it in the next planned service
   restart, not mid-conversation:

   1. edit `~/.config/systemd/user/hass-receiver.service` and `hass-worker.service` as above
   2. `systemctl --user daemon-reload`
   3. `systemctl --user restart hass-receiver.service hass-worker.service` (the planned restart)
   4. `systemctl --user status hass-receiver.service hass-worker.service` shows both running

## Check

`~/.local/share/hass/venv/bin/python3 -c "import PIL; print(PIL.__version__)"` must print `12.0.0`.

Then, from the runtime worktree, run the same guard test CI runs:

`~/.local/share/hass/venv/bin/python3 -m unittest discover -s tests -p test_pillow_ci.py -v`

It must say `OK`. Without Pillow it fails with `ModuleNotFoundError: No module named 'PIL'`.

## Changing the version

Change `PILLOW_VERSION` in `check.yml` and the version in step 2 above in the same pull request, then
the operator repeats step 2. Do not use `pip install Pillow` without the `==` pin, and do not upgrade on
the host alone.

## The Mac mini

Hass picture rendering runs on AgentOrange, not on the Mac. The Mac side only sends and receives
attachments, so it needs no Pillow. If that ever changes, install the same pinned version there.
