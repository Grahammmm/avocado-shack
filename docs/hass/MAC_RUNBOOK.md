# Hass: G-only Mac-to-live runbook

G performs every step; no agent signs in, handles secrets, sends texts, enables services or publishes.
Stop at any unexpected result; leave drafts unapproved. This document enables nothing.
Replace `<...>` privately, never literally; use absolute paths in JSON (no `~`). Shell commands are for G's console.
Never put a secret, owner address, phone, chat id or IP in chat, a card, an agent, clipboard sync, Git or logs.
UI labels below are provisional; step 18 records actual versions/names. Taildrop is UNVERIFIED on this tailnet.

## Phase A — Mac and accounts (no code needed)

1. **G / Mac:** Record H07 privately: model and macOS version. In Users & Groups (UNVERIFIED until step 18), create a dedicated standard user; enable FileVault (UNVERIFIED until step 18), disable automatic login (UNVERIFIED until step 18). Run `csrutil status`.
   Expected: standard user, encrypted disk, no automatic login, System Integrity Protection enabled.
   <!-- step 1 needs: - makes: mac-user -->
2. **G / Mac:** In that user, sign into the business Apple Account in Messages (UNVERIFIED until step 18); enable its email iMessage address in Send & Receive (UNVERIFIED until step 18). G retains all 2FA codes.
   Expected: the owner's test text arrives; G's manual reply reaches the phone. Record the one-to-one owner chat privately.
   <!-- step 2 needs: mac-user makes: imessage -->
3. **G / Mac:** Run `sudo pmset -a sleep 0 disksleep 0 autorestart 1`; the display may sleep. Set Messages → Keep messages: 1 Year (UNVERIFIED until step 18), H21.
   Expected: Mac stays awake and restarts after power loss; message retention is one year.
   <!-- step 3 needs: mac-user,imessage makes: - -->
4. **G / Mac:** Install Python 3.12 from python.org; run `python3.12 --version`.
   Expected: Python 3.12; record the installed executable's absolute path for step 14.
   <!-- step 4 needs: mac-user makes: mac-python -->
5. **G / Mac:** Install the official Tailscale app and sign into the tailnet via Log in (UNVERIFIED until step 18).
   Expected: Mac and AgentOrange visible in Machines (UNVERIFIED until step 18); record node names privately.
   <!-- step 5 needs: mac-user makes: mac-tailnet -->
6. **G / account website + AgentOrange:** In Tailscale Access controls (UNVERIFIED until step 18), allow only this Mac to reach `agentorange:8795`; enable Taildrop (UNVERIFIED until step 18) only between these machines. If receiving files requires it, G runs `sudo tailscale set --operator=$USER` on AgentOrange.
   Expected: only the Mac has this network access; file transfer works. If Taildrop is unavailable, G carries the step-11 bundle on USB and uses the step-15 typed-key fallback; do not broaden access.
   <!-- step 6 needs: mac-tailnet makes: acl,taildrop -->
7. **G / Mac:** Install BlueBubbles Server from its official release. Grant only prompted permissions in Privacy & Security (UNVERIFIED until step 18); keep Private API (UNVERIFIED until step 18) off.
   Expected: server sees the business Messages account without the Private API.
   <!-- step 7 needs: imessage makes: bb -->
8. **G / Mac:** Generate a server password with `openssl rand -hex 24` only at G's private console; set Server password (UNVERIFIED until step 18) in BlueBubbles. Disable every proxy and dynamic-DNS option (UNVERIFIED until step 18). Enable Firewall (UNVERIFIED until step 18) in macOS.
   Run `lsof -nP -iTCP -sTCP:LISTEN`. Expected: BlueBubbles REST reachable only on loopback; no non-loopback listener admitted by the firewall. Stop if not enforceable.
   <!-- step 8 needs: bb makes: bb-password -->
9. **G / Mac:** Create private local files; enter the step-8 password into `bb-password` using a private local editor, not shell history:
   ```sh
   umask 077
   mkdir -p ~/Library/Application\ Support/HassForwarder
   cd ~/Library/Application\ Support/HassForwarder
   openssl rand -hex 32 > envelope.key
   openssl rand -hex 32 > webhook.token
   chmod 600 envelope.key webhook.token bb-password
   ```
   Expected: three 0600 files in a 0700 directory; secrets created on the using machine, no synced clipboard or logs.
   <!-- step 9 needs: bb-password makes: mac-secrets -->

## Phase B — Reviewed code (all HASS units merged)

10. **G / AgentOrange:** Pick and privately record `<R>`: reviewed main containing HASS-RCV-1, LIVEPOL-1, FWD-1, ATTACH-1, PUBLISH-1, SVC-1 and MAC-RUNBOOK. Use existing GitHub access here only:
    ```sh
    umask 077
    mkdir -p ~/.local/share/hass ~/.local/state/hass/{state,host,backups} ~/.config/hass
    git clone https://github.com/Grahammmm/avocado-shack ~/.local/share/hass/avocado-shack
    git -C ~/.local/share/hass/avocado-shack log --oneline origin/main
    git -C ~/.local/share/hass/avocado-shack worktree add --detach ../runtime <R>
    git -C ~/.local/share/hass/avocado-shack worktree add -b hass/live ../writer <R>
    git -C ~/.local/share/hass/writer config user.name '<chosen identity>'
    git -C ~/.local/share/hass/writer config user.email '<chosen commit address>'
    cd ~/.local/share/hass/runtime
    python3 hass/acceptance.py
    ```
    Expected: all named merges at/before R and no real acceptance failure. Runtime stays clean/detached at R; writer starts at R. Never run services from the old live-site build commit. Commits are signed off.
    <!-- step 10 needs: - makes: R,runtime,writer -->
11. **G / AgentOrange → Mac:** The repo is private; put no GitHub credential on the Mac. Transfer code without requiring an SSH server:
    ```sh
    git -C ~/.local/share/hass/avocado-shack bundle create ~/hass-R.bundle hass/live
    tailscale file cp ~/hass-R.bundle <mac node>:
    ```
    On Mac: `tailscale file get ~/Downloads` (or Receive files (UNVERIFIED until step 18)); `mkdir -p ~/hass`; `git clone ~/Downloads/hass-R.bundle ~/hass/avocado-shack`; `git -C ~/hass/avocado-shack checkout --detach <R>`; `git -C ~/hass/avocado-shack rev-parse HEAD`.
    Expected: HEAD equals R. G deletes only the transfer bundle on both machines after verification. USB fallback preserves this R check.
    <!-- step 11 needs: R,taildrop makes: mac-code -->

## Phase C — Mac forwarder

12. **G / Mac:** Create the spool with `umask 077; mkdir -p ~/Library/Application\ Support/HassForwarder/spool`. Privately write `~/Library/Application Support/HassForwarder/config.json`; use the same owner one-to-one chat recorded in step 2:
    ```json
    {"ownerChat":"iMessage;-;<owner address>","receiverUrl":"http://<agentorange tailnet name>:8795","bbPort":<BlueBubbles port>,"bbPasswordFile":"<absolute support path>/bb-password","secretFile":"<absolute support path>/envelope.key","spoolDir":"<absolute support path>/spool","webhookPort":8796,"ack":true,"webhookTokenFile":"<absolute support path>/webhook.token"}
    ```
    Run `chmod 600 ~/Library/Application\ Support/HassForwarder/config.json`. Expected: private config, spool 0700, actual integer bbPort and absolute file paths.
    <!-- step 12 needs: mac-secrets,mac-code makes: fwd-config -->
13. **G / Mac:** In BlueBubbles Webhooks (UNVERIFIED until step 18), add `http://127.0.0.1:8796/bb/<token>` using the local webhook.token value; select only new-message and updated-message (UNVERIFIED until step 18).
    Expected: loopback-only doorbells for those two events; token never leaves the private setup.
    <!-- step 13 needs: bb,mac-secrets makes: webhook -->
14. **G / Mac:** Fill `~/hass/avocado-shack/mac/com.avocadoshack.hass-forwarder.plist.template` into `~/Library/LaunchAgents/com.avocadoshack.hass-forwarder.plist`: replace `@PYTHON@`, `@REPO@`, `@CONFIG@`, `@LOGDIR@` with absolute Python 3.12, repo, config and private log-directory paths. Create directories with `umask 077; mkdir -p ~/Library/LaunchAgents ~/Library/Application\ Support/HassForwarder/logs`; use that private logs directory for `@LOGDIR@`.
    Run `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.avocadoshack.hass-forwarder.plist`, then `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json`.
    Expected: forwarder running; BlueBubbles reachable. Before step 17 the combined check may report `{"error":1}` because the receiver is absent; verify BlueBubbles locally rather than treating that as success.
    <!-- step 14 needs: fwd-config,mac-python,webhook makes: forwarder -->

## Phase D — Receiver and first private yes

15. **G / Mac → AgentOrange:** Run `tailscale file cp ~/Library/Application\ Support/HassForwarder/envelope.key <agentorange node>:` on Mac. At AgentOrange:
    ```sh
    umask 077
    mkdir -p ~/.config/hass/in
    tailscale file get ~/.config/hass/in
    mv ~/.config/hass/in/envelope.key ~/.config/hass/envelope.key
    chmod 600 ~/.config/hass/envelope.key
    ```
    Fallback: G reads the key on the Mac screen and types it at AgentOrange's own Bash console: `umask 077; read -rs K; printf '%s\n' "$K" > ~/.config/hass/envelope.key; unset K`.
    Compare privately: Mac `shasum -a 256 ~/Library/Application\ Support/HassForwarder/envelope.key | cut -c1-12`; AgentOrange `sha256sum ~/.config/hass/envelope.key | cut -c1-12`.
    Expected: matching short hashes, host key 0600; no key through chat, card, agent, commit, clipboard sync or log.
    <!-- step 15 needs: mac-secrets,taildrop makes: host-key -->
16. **G / AgentOrange runtime:** `cd ~/.local/share/hass/runtime`; `python3 hass/editor.py init --state ~/.local/state/hass/state --worktree ~/.local/share/hass/writer`. Privately edit state's config.json `settings`: `ownerSenders` = ["<owner address>"], `ownerChat` = "iMessage;-;<owner address>", `approvalTtlSeconds` = 3600, `interpreterDailyCap` = a G-chosen integer 1–10000; no `liveSite` yet.
    Write `~/.local/state/hass/host/host.json` BEFORE start-point (it requires --host), mode 0600:
    ```json
    {"state":"<absolute state path>","secretFile":"<absolute home>/.config/hass/envelope.key","listen":"<agentorange tailnet IP>:8795","allowedPeers":["<Mac tailnet IP>"],"approvals":"hold","runtimeCommit":"<R>","interpreter":{"url":"http://127.0.0.1:11434","model":"<existing approved local model>"},"previewer":true,"pictures":true}
    ```
    `python3 hass/host.py start-point --host ~/.local/state/hass/host/host.json --at '<now ISO>'`; `python3 hass/host.py check --host ~/.local/state/hass/host/host.json`.
    Expected: ok, immutable start point; key and runtime validated, approvals held. Existing approved interpreter and screenshot runtime must be available; stop if missing, do not install/change a model here.
    <!-- step 16 needs: R,runtime,writer,host-key makes: state,host-config -->
17. **G / AgentOrange + Mac:** `mkdir -p ~/.config/systemd/user`; `cp ~/.local/share/hass/runtime/deploy/hass/* ~/.config/systemd/user/`; `systemctl --user daemon-reload`; `systemctl --user enable --now hass-receiver hass-worker hass-health.timer hass-backup.timer`.
    On Mac repeat `python3.12 ~/hass/avocado-shack/mac/hass_forwarder.py check --config ~/Library/Application\ Support/HassForwarder/config.json`.
    Expected: units active and `{"reachable":2}`; no services run from writer or historical live-site code.
    <!-- step 17 needs: host-config,host-key,forwarder,acl makes: services -->
18. **G / owner chat + AgentOrange runtime:** Follow CONNECT.md smoke checks in order: (1) owner texts `status`, gets one reply; (2) stranger's text gets no reply and no draft; (3) owner requests a small change, gets a draft, replies `no`, nothing changes; (4) run `python3 hass/inbox.py status --state ~/.local/state/hass/state`, messages done and none pending.
    Expected: all four pass. Record BlueBubbles, macOS and Python versions and real UI names privately (H07); until this passes every UI label remains UNVERIFIED.
    <!-- step 18 needs: services makes: smoke-ok -->
19. **G / Mac + owner chat + AgentOrange runtime:** `launchctl bootout gui/$(id -u)/com.avocadoshack.hass-forwarder`; owner texts `status` during a two-minute outage; restart using step 14's bootstrap. Expected: one late-headed reply after recovery.
    Set host `approvals` to `private`; `systemctl --user restart hass-worker`. Owner requests a small change and replies `yes <code>`. Expected: writer gains a `hass content:` commit and the phone receives a result **picture**. Owner sends `undo <code>`, then `yes <undo code>`. Cancelled, expired, duplicate or stale approvals must not create another commit; request a fresh draft rather than retrying an old code.
    Stop here if no picture arrives, undo fails, or recovery duplicates a reply. Live mode requires picture delivery.
    <!-- step 19 needs: services,smoke-ok makes: picture-ok -->

## Phase E — Live access, adoption, go live, stop

20. **G / AgentOrange + account websites:** `ssh-keygen -t ed25519 -N "" -C hass-site -f ~/.ssh/hass_site` (do not overwrite an existing key). In private `~/.ssh/config` add:
    ```sshconfig
    Host github-avocadoman
      HostName github.com
      User git
      IdentityFile ~/.ssh/hass_site
      IdentitiesOnly yes
    ```
    On GitHub, theavocadoman-site only: Settings → Deploy keys → Allow write access (UNVERIFIED until step 18). G views `~/.ssh/hass_site.pub` locally and adds that public key. Run `ssh -T git@github-avocadoman`; verify the host fingerprint against GitHub's published fingerprints BEFORE accepting.
    Expected: greeting identifies theavocadoman-site (GitHub may exit 1 without shell access), no account-wide credential. In Cloudflare Pages project settings (UNVERIFIED until step 18), disable HTML rewriting including email obfuscation.
    <!-- step 20 needs: - makes: deploy-key,ssh-alias -->
21. **G / AgentOrange runtime:** `git clone git@github-avocadoman:Grahammmm/theavocadoman-site.git ~/.local/share/hass/theavocadoman-site`; set checkout identity with `git -C ~/.local/share/hass/theavocadoman-site config user.name '<chosen identity>'` and `git -C ~/.local/share/hass/theavocadoman-site config user.email '<chosen commit address>'`. Add `release` to host.json (preserve 0600):
    ```json
    {"siteCheckout":"<absolute site checkout>","siteRemote":"git@github-avocadoman:Grahammmm/theavocadoman-site.git","liveUrl":"https://theavocadoman.com","stopFile":"<absolute home>/.config/hass/STOP","dailyCap":10,"minIntervalSeconds":120,"verifyMinutes":15}
    ```
    `cd ~/.local/share/hass/runtime`; `python3 hass/publish_live.py adopt --host ~/.local/state/hass/host/host.json`.
    If `differs`: `python3 hass/publish_live.py adopt --from-remote --host ~/.local/state/hass/host/host.json`, then `python3 hass/publish_live.py baseline --host ~/.local/state/hass/host/host.json`. G reads path count and privacy ids; ONLY if expected, run `python3 hass/publish_live.py baseline --host ~/.local/state/hass/host/host.json --confirm <manifest>`.
    Expected: adoption reconciles writer R to live bytes; remote adoption is only a baseline anchor. Confirmed baseline is a G live publication, refused with STOP present. `python3 hass/publish_live.py status --host ~/.local/state/hass/host/host.json` shows live baseline (if needed), no open release. Stop on unknown/unexpected differences.
    <!-- step 21 needs: R,runtime,writer,deploy-key,ssh-alias,host-config makes: site-checkout,release-config,adopted -->
22. **G / AgentOrange + owner chat:** Only after picture and adoption pass, set state settings `liveSite` = `theavocadoman.com`, `approvalNeedsCode` = true; set host `approvals` to `live`; `systemctl --user restart hass-worker`.
    Michael chooses one low-risk change, e.g. headline, replies `yes <code>`. Expected: “Saved”, then “Now showing on theavocadoman.com” with a picture. G checks `https://theavocadoman.com` and `python3 hass/publish_live.py status --host ~/.local/state/hass/host/host.json` from runtime: no open release. Stop on missing picture, expired/stale code or unknown release; do not blindly retry.
    <!-- step 22 needs: adopted,release-config,picture-ok,services,runtime makes: live -->
23. **G / both machines:** Mac: `launchctl bootout gui/$(id -u)/com.avocadoshack.hass-forwarder`, then Quit BlueBubbles (UNVERIFIED until step 18). AgentOrange: `touch ~/.config/hass/STOP`; `systemctl --user stop hass-worker hass-receiver hass-health.timer hass-backup.timer hass-health.service hass-backup.service`.
    Expected: forwarding, processing and timers stopped; STOP prevents publication. Leave drafts unapproved. Optionally remove the Tailscale ACL and GitHub deploy key in their account settings (UNVERIFIED until step 18).
    Emergency rollback: G uses Cloudflare Pages → Rollback (UNVERIFIED until step 18), then from runtime `python3 hass/publish_live.py resolve <change id> --as reverted --host ~/.local/state/hass/host/host.json` only after checking the actual site. Preserve journals; unknown is not success.
    <!-- step 23 needs: runtime makes: stopped -->
