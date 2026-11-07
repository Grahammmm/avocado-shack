# Hass Mac mini: G's final steps (HASS-MAC-KIT-1)

What this is: the short list of things only G can do at the Mac mini to get BlueBubbles ready for the Hass bridge.
Everything else is in two scripts ([`mac_install.sh`](../../scripts/hass/mac_install.sh), [`mac_setup_check.sh`](../../scripts/hass/mac_setup_check.sh)).
This document enables nothing and sends nothing by itself. It adds to, and does not replace, [MAC_RUNBOOK.md](MAC_RUNBOOK.md);
when the two differ, the runbook wins and the difference is listed in "Where this differs from the runbook" below.

**Total G time (estimate, UNVERIFIED): about 42 minutes, up to 62 if Apple holds the new Apple Account for verification.**
Per step in brackets. Steps 1-4 are Apple-side; 5-10 are the install and firewall; 11 is optional.

Rules that stay in force: no agent logs in anywhere; nothing here reads or changes anything outside the new Hass user and
the new BlueBubbles setup (this Mac also holds farm data, so everything is done in a **separate new macOS user**); never put
a password, key, phone number, address or IP into chat, a card, Git or a log. Replace `<...>` privately.
Labels marked UNVERIFIED are written from documentation, not from this Mac; step 11 records the real names.

## Before you start (on AgentOrange, 1 minute)

Send the two scripts to the Mac over Tailscale (Taildrop is UNVERIFIED on this tailnet; if it fails, copy the two files by USB stick or AirDrop):

```sh
tailscale file cp ~/.local/share/hass/runtime/scripts/hass/mac_install.sh ~/.local/share/hass/runtime/scripts/hass/mac_setup_check.sh <mac node name>:
```

(The path assumes the runbook step 10 runtime checkout of reviewed main that includes this kit.)

## Steps at the Mac mini

1. **[3 min] Create a new standard macOS user for Hass.** Apple menu > System Settings > Users & Groups > Add User…, Account Type **Standard**, name it `hass`; leave "Allow user to administer this computer" off, then log in as `hass` (Apple menu > Log Out…). Why: keeps Messages, BlueBubbles and the kit completely apart from the farm's user and data.
2. **[10 min] Create the dedicated Apple Account.** In Safari on this Mac open `https://account.apple.com`, choose **Create Your Apple Account**, use a **new email address you control** as the Apple ID (Michael will text this address), and finish the verification with G's own phone. No iPhone is needed for iMessage; do not add a phone number to this account.
3. **[5 min] Sign Messages in and turn on the email address.** Open Messages > Messages menu > Settings… > iMessage > **Sign in** with that Apple Account, then under "You can be reached for messages at" tick the email address and set "Start new conversations from" to it (labels UNVERIFIED).
4. **[3 min] Send a test message both ways.** From G's own phone (or any iMessage device) text that Apple ID email address `hass kit test 1`, then reply from Messages on the Mac. Expect: the text arrives, the reply reaches the phone. Texting the account from itself does not work reliably, so use a second device (UNVERIFIED). This proves iMessage works with no SMS and no iPhone on the Mac.
5. **[5 min] Install Tailscale and join the tailnet.** Download the official macOS app from `https://tailscale.com/download`, open it, and use **Log in** with G's tailnet account; expect the Mac to appear in the Machines list (runbook step 5 has the access-control step 6, which is G on the account website, not at this Mac).
6. **[2 min] Fetch the two scripts.** In Terminal (Applications > Utilities > Terminal) paste:
   ```sh
   /Applications/Tailscale.app/Contents/MacOS/Tailscale file get ~/Downloads && ls ~/Downloads/mac_install.sh ~/Downloads/mac_setup_check.sh
   ```
   Expect both file names listed. (USB or AirDrop users: put the files in `~/Downloads`.)
7. **[5 min, mostly download] Run the installer.** Paste this; it prints the pinned file name, size and sha256, compares them with the live GitHub release page, refuses on any difference, downloads about 300 MB, installs `~/Applications/BlueBubbles.app`, and creates the launch-at-login and keep-awake items. It needs no sudo.
   ```sh
   bash ~/Downloads/mac_install.sh
   ```
   Expect the last lines "Done with the automatic part". Run it again any time; it skips what is done. First use `bash ~/Downloads/mac_install.sh --print-plan` if you want to see the pinned values with nothing downloaded.
8. **[8 min] Approve the macOS permission prompts BlueBubbles shows.** BlueBubbles opens by itself; in its setup wizard click through and, when macOS asks, allow **Full Disk Access** (System Settings > Privacy & Security > Full Disk Access, switch BlueBubbles on) and **Automation > Messages** (the "BlueBubbles wants to control Messages" prompt); allow **Accessibility** only if the app asks for it, and Notifications are optional (all UNVERIFIED; names can differ by macOS version). Do **not** enable Private API, do **not** change System Integrity Protection, and choose no proxy, tunnel or dynamic-DNS option. If macOS says it cannot verify the app, right-click the app > Open once (UNVERIFIED).
9. **[3 min] Set the BlueBubbles server password privately.** In the BlueBubbles window set the **Server password** (generate with `openssl rand -hex 24` in your own Terminal, type it only into the BlueBubbles field and into the runbook step 9 `bb-password` file; the kit never sees it). Note the port shown (default 1234).
10. **[2 min] Turn on the macOS firewall (runbook step 8).** System Settings > Network > Firewall > on (older macOS: Privacy & Security > Firewall); leave \"Block all incoming connections\" off so Tailscale keeps working (UNVERIFIED). Then paste `lsof -nP -iTCP -sTCP:LISTEN` and confirm BlueBubbles' port shows only `127.0.0.1`/`localhost`. **Stop** if it listens on `*` or any other address; do not go on until loopback-only is enforced.
11. **[optional, 3 min] Remote Login for AgentOrange.** Not needed for the bridge (the runbook moves code and keys with Taildrop and the Mac initiates all traffic). Only if G wants AgentOrange to be able to log in: System Settings > General > Sharing > **Remote Login** on, "Allow access for: Only these users" > add only `hass`; then paste (replacing the quoted text with the one-line **public** key printed by `cat ~/.ssh/<AgentOrange key name>.pub` on AgentOrange; never a private key):
    ```sh
    mkdir -p ~/.ssh && chmod 700 ~/.ssh && printf '%s\n' '<AgentOrange public key line>' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
    ```
12. **[2 min] Run the checker and the 3-minute test.** Paste (replace the node name and port if different):
    ```sh
    RECEIVER_HOST=<agentorange tailnet name> BB_PORT=1234 bash ~/Downloads/mac_setup_check.sh
    ```
    Expect no `FAIL` lines (a `FAIL` on loopback-only or the firewall means stop and fix before anything else; a `WARN` about Messages is a manual check of Messages > Settings > iMessage). A `WARN` about port 8795 is normal until the receiver is started (runbook step 17). Then do the test plan below, and record the real UI names and versions privately (H07).

Then continue the runbook at step 9 (forwarder secrets). Steps 1-8 of the runbook (including the firewall, step 10 here) are covered above, except the dedicated-user FileVault/auto-login settings (runbook step 1) and the Python install (step 4); do those from the runbook.

## Keep-awake

The installer creates a per-user `caffeinate -i -s` login item (label `com.avocadoshack.hass-keepawake`) so the Mac does not sleep while Hass is signed in, without sudo and without changing any system power setting. The runbook's `sudo pmset -a sleep 0 disksleep 0 autorestart 1` is stronger and also restarts after a power cut; G may still run it (it changes machine-wide power settings, which also affect the farm user, so it is G's call). The checker passes on either.

## 3-minute test plan (G, after the steps; synthetic content only)

Prerequisites: runbook steps through 17 done (forwarder running, receiver active). Use only the words below; no real customer text, no photos.

1. **Reach the receiver (1 min).** From the owner address's phone send `status` to the dedicated Apple ID email. Expect: within about a minute one reply arrives on the phone. UNVERIFIED end to end until this runs.
2. **See it arrive (1 min).** On AgentOrange: `cd ~/.local/share/hass/runtime && python3 hass/inbox.py status --state ~/.local/state/hass/state`. Expect: one message counted, none pending.
3. **See a reply go back (30 s).** The reply from step 1 is the proof. If none: on the Mac run `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json` and expect `{"reachable":2}`.
4. **Stranger check (30 s).** From any other iMessage account send `hass kit test 2`. Expect no reply and no draft.

Pass = steps 1-4 as expected. On any other result: stop, leave drafts unapproved, run the checker, and see [BRIDGE_WIRING.md](BRIDGE_WIRING.md).

## Where this differs from the runbook (for the reviewer)

- The task asked the checker to test the BlueBubbles port "over Tailscale". The runbook (step 8) keeps BlueBubbles loopback-only, so the checker requires loopback, **fails** (stop) if it listens wider or cannot be verified, and also fails if the firewall is off or unreadable, and tests the receiver port 8795 on AgentOrange over Tailscale instead.
- Keep-awake uses a `caffeinate` login item instead of required `sudo pmset`; pmset stays optional.
- Everything about the real Mac (labels, prompts, Messages sign-in hint, firewall-state command, `launchctl` behaviour, whether Gatekeeper asks) is UNVERIFIED; nothing here was run on it.
