# Hass support path (H17/H19)

The operator runs `python3 hass/health.py --state DIR [--backups DIR] [--seen FILE]` on Agent Orange. It prints one JSON line;
exit 0 is ok, 1 means problems, 2 means unsafe (nothing else was checked). Each problem names a check id and a short detail
(counts or codes only). With `--seen FILE`, `notify` is true only when the set of problems changed.
The owner's first move is always the chat command `status`. The support contact and account ownership are recorded privately
by the owner/G (H22), never in Git. Read-only checks come first; anything that writes state happens only after `pause changes`.

## Reader not working

When Hass could not reach the model or got no usable answer, it replies "I couldn't work that out just now, so nothing was changed. Please try again in a few minutes." and `status` adds "I couldn't read your request from <time>. Could you send it again?" (HASS-VOICE-1 wording). Nothing is retried automatically, and it was not the owner's wording. When the failed request was a photo's caption, the photo's needs-details draft was already opened: `status` then says to reply to that draft with the product and description (sending the same photo again only answers "already in draft" and does not read the caption). The line stays until a later change request is read. This is a chat status indication, not a health problem id.

- **Owner:** send the change again once the reader is back; Hass never replays it for you.
- **Operator:** if it repeats, run `python3 hass/health.py --state DIR` and check the model there. Do not edit the queue or restart anything for this alone; contact the support person recorded privately.
- **Slow model:** the reader waits `interpreter.timeout` seconds (default 30) and then gives up as above. If the model is slow (for example it runs on CPU), the operator may set `"timeout"` (whole seconds, 1 to 120) and, to skip the model's reasoning phase, `"think": false` in the `interpreter` object of `host.json`, run `python3 hass/host.py check --host host.json` (it rejects other keys and bad values), then restart the receiver and worker at an attended moment. The repo never edits `host.json` or restarts anything.

## Problems

### `state`
- **Means:** the state dir is missing, a symlink, shared (not mode 0700), owned by someone else, inside the repository or the writer worktree, or not initialised. Exit 2; no other check ran.
- **Check first:** `ls -ld DIR` and the exact `--state` path the services use; re-run `python3 hass/health.py --state DIR`.
- **Next step:** correct the path given to the check. Never run `python3 hass/editor.py init` over a dir that held live state.
- **Stop and ask:** the dir vanished or its owner or mode changed without a known reason, or the only copy left is a backup (any restore onto the writer worktree is attended).

### `settings`
- **Means:** `<state>/config.json` fails the settings check; the detail names the fields.
- **Check first:** read the detail; `python3 hass/editor.py history --state DIR --limit 5` shows when changes last went through.
- **Next step:** after `pause changes`, the operator corrects only the named fields from the owner's recorded values, re-runs the check, then the owner sends `resume changes`.
- **Stop and ask:** a value only the owner/G knows (owner senders, chat, guest-count database), or `config.json` is missing.

### `db-integrity`
- **Means:** `conversation.sqlite3` fails its quick check (`<n> issue(s)`) or cannot be opened (`database unreadable`).
- **Check first:** re-run the check once; `python3 hass/statebackup.py verify BACKUP` on the newest backup.
- **Next step:** `pause changes` if the chat still answers; leave the damaged file untouched; run the isolated restore drill (below) to see what the newest good backup holds.
- **Stop and ask:** always before a live restore, when `db-integrity` repeats on a second run, or before any edit, copy over or deletion of the file.

### `state-db`
- **Means:** `conversation.sqlite3` or `inbox.sqlite3` in the state dir is a symlink (dangling too), a directory or another non-regular file; health never opened it.
- **Check first:** `ls -l DIR/conversation.sqlite3 DIR/inbox.sqlite3`.
- **Next step:** none in the repo: leave the entry and whatever it points at untouched.
- **Stop and ask:** always; the real database may be elsewhere or gone (before any move, copy or deletion).

### `outbox-stuck`
- **Means:** replies have waited unsent longer than `--outbox-minutes`; the detail is the count. The Mac bridge or the sender is failing.
- **Check first:** the owner sends `status`; if no reply arrives the outbound path is down. Re-run the check after a few minutes to see whether the count moves.
- **Next step:** none in the repo: there is no resend command. Leave the outbox rows as they are.
- **Stop and ask:** before any manual or live send or outbox edit, and when the count persists across two checks (the Mac side is owner/G work).

### `apply-stuck`
- **Means:** drafts were approved more than 10 minutes ago but not applied; the detail is the count. The writer stopped between approval and apply.
- **Check first:** `python3 hass/editor.py history --state DIR --limit 5` and `python3 hass/editor.py show CHANGE_ID --state DIR`.
- **Next step:** after `pause changes`, `python3 hass/editor.py recover --state DIR` settles a pending journal (`busy` means the writer is still running: wait). Then the owner sends `status` and `resume changes`.
- **Stop and ask:** `recover` fails or reports a conflict, the writer worktree is not clean, or the count stays after `recover`. Never re-run `apply` by hand.

### `unverified`
- **Means:** a change was applied but its preview screenshot check failed, within `--unverified-hours` (default 72); the detail is the count. An undo does not clear it (the site was changed unchecked); it clears once the window passes.
- **Check first:** the owner sends `status` (the last change line shows `not verified: …`), or `python3 hass/editor.py history --state DIR --limit 5`.
- **Next step:** look at the live page for that change; if it is wrong, the owner sends `undo <code>`.
- **Stop and ask:** before re-applying or editing the site by hand, or when the count rises on every change.

### `backup-age`
- **Means:** with `--backups`: no complete `hass-state-*` backup within `--backup-hours`, no complete backup at all, the backup dir is unreadable, or the newest complete backup's name is dated after this box's clock (`timestamp is in the future`; it is not verified and no older backup is used instead).
- **Check first:** `ls -l BACKUPS`; `python3 hass/statebackup.py verify BACKUP` on the newest one. For a future timestamp, check this box's clock (`date -u`) against the newest backup name; do not rename, delete or touch any backup.
- **Next step:** `python3 hass/statebackup.py create --state DIR --out BACKUPS` (OUT mode 0700). It reads state only; `busy` means retry later, `unsettled` means `recover` first (after `pause changes`).
- **Stop and ask:** `create` answers `refused` (backups include `inbox.sqlite3`; a leftover `inbox.sqlite3-journal` is refused as an unknown entry) or `verify` answers `corrupt`, the disk is full, or a backup timer needs installing (attended).

### `backup-verify`
- **Means:** with `--backups`: the newest complete backup within `--backup-hours` fails `statebackup.verify` (detail: problem count, or `verify failed`). Only the newest is judged; an older good one does not clear it.
- **Check first:** `python3 hass/statebackup.py verify <dir>` on that newest backup (names the damaged entries; health never does).
- **Next step:** after `pause changes`, make a fresh backup with `python3 hass/statebackup.py create --state DIR --out BACKUPS`; keep the corrupt one for inspection.
- **Stop and ask:** every recent backup is corrupt.

### `seen`
- **Means:** `--seen FILE` is a symlink, lies inside the repository or the state dir, or its folder is missing. Exit 2; no other check ran.
- As an `info` entry `seen file not updated`: the check ran but its folder could not be written; `notify` is forced true. Check free space and the folder's owner/mode.
- **Check first:** `ls -l` on the seen path and its folder.
- **Next step:** point `--seen` at a plain file in an existing folder outside both (a missing file is created on the next run).
- **Stop and ask:** the file turned into a symlink without a known reason.

### `inbox-stuck`
- **Means:** inbound messages have stayed pending in `<state>/inbox.sqlite3` longer than `--inbox-minutes`; the detail is the count. The drain is not running or one message keeps failing.
- **Check first:** the owner sends `status`; re-run the check to see whether the count moves.
- **Next step:** none in the repo: there is no drain command. Leave the queue as it is; pending messages are handed on in order once the drain runs.
- **Stop and ask:** before any service restart (attended), queue edit or deletion; when the count persists across two checks.

### `inbox-unreadable`
- **Means:** inbound messages in `inbox.sqlite3` could not be read and were skipped within `--inbox-unreadable-hours` (default 24); the detail is the count. No message text is kept; the problem clears by itself after the window.
- **Check first:** re-run the check once; `inbox-integrity` alongside it means the queue file itself is damaged.
- **Next step:** ask the owner to resend their last message(s); leave the queue as it is.
- **Stop and ask:** before any queue edit or deletion; when the count keeps rising across checks.

### `inbox-integrity`
- **Means:** `inbox.sqlite3` fails its quick check (`<n> issue(s)`) or cannot be opened (`database unreadable`).
- **Check first:** re-run the check once; `python3 hass/statebackup.py verify BACKUP` on the newest backup (it checks that backup's `inbox.sqlite3` snapshot).
- **Next step:** `pause changes` if the chat still answers; leave the damaged file untouched; run the isolated restore drill (below) to see whether the newest good backup's inbox snapshot is intact. A restored inbox can replay or miss messages received after that backup.
- **Stop and ask:** always. Recreating the queue needs a new start point, which the owner/G decides. Always before any live replacement of `inbox.sqlite3` (attended).

### `writer`
- **Means:** with `--writer`: one entry per reason `apply` would refuse the recorded writer worktree: `uncommitted changes`, `branch main` or `detached HEAD` refused, `git user.name`/`user.email` not configured, `main checkout` refused, not the top of a Hass checkout (moved or deleted), or `config.json` missing (`not initialised`) or unreadable. Git runs read-only; no path is printed.
- **Check first:** `git -C WT status` and `git -C WT branch --show-current` on the worktree recorded in `config.json`.
- **Next step:** after `pause changes`, commit or stash in the writer worktree, switch it to a non-main branch, or set its Git identity; re-run the check, then the owner sends `resume changes`.
- **Stop and ask:** the worktree is gone or is the main checkout (re-running `python3 hass/editor.py init` onto a new linked worktree is attended), or changes there are not known.

### `model`
- **Means:** with `--model` (a loopback address only): the local model did not answer `/api/tags` within 3 s (`unreachable`), answered with an error status (`http <status>`), sent something that is not a model list (`bad reply`), or the `--model-name` model is missing (`model not installed`; a name without a tag means `:latest`). No URL or reply text is printed.
- `--label-model NAME` checks the FAV-03 label reader's vision model on the same server in that one reply: `interpreter model not installed`, `label model not installed`, or `interpreter and label models not installed`; without `--model-name`, only the label model is checked. Names without a tag mean `:latest`; no model name is printed.
- **Check first:** `ollama list` on Agent Orange, and whether the Ollama service is running; re-run the check once.
- **Next step:** none in the repo: health only reads and never restarts or changes the model.
- **Stop and ask:** always before restarting Ollama, pulling or changing a model, or editing its service (attended; tell the operator).

### `guest-counts`
- **Means:** `unreadable`: the configured RSVP database (`guestCountsDb`) cannot be opened read-only; `unset`: RSVPs are on for an upcoming hike but no RSVP database is configured. Status shows `guest count unavailable` and capacity edits are refused. As an `info` entry `hikes unreadable`: the setting is unset and the writer worktree's `community.json` could not be read. No path is printed.
- **Check first:** the file exists and is readable by the Hass user.
- **Next step:** fix the `guestCountsDb` setting in the private config (attended).
- **Stop and ask:** before editing or copying the RSVP database (it holds guests' names).

### `memory-invariant`
- **Means:** owner memory breaks its rules: two current values for one name, or a forgotten fact's text still stored (`<n> row(s)`; `memory table unreadable` when the rows cannot be read). No name, value or source is printed.
- **Check first:** re-run the check once; ask the operator to open `conversation.sqlite3` read-only to see which names are affected.
- **Next step:** `pause changes`, then restore the newest verified backup into a drill dir (`python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused`) and compare its memory history to find when the rule broke.
- **Stop and ask:** before editing the database by hand: blanking leftover forgotten text or retiring a second current row is an attended operator change; the owner's `forget`/`remember` commands cannot fix either.

### `media-store`
- **Means:** with `--media DIR`, the private photo store has a damaged, missing or stray file (`<n> problem(s)`); `media store unsafe` when the dir is missing, a symlink, or inside the repository or the state dir; `media store unreadable` when it cannot be read. No file name or hash is printed.
- **Check first:** `python3 hass/media.py verify --root DIR` (read-only; names 12-character sha prefixes only).
- **Next step:** restore the named originals from the newest verified backup into a drill dir first (`python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused --media-into NEWMEDIA`), then copy only those originals back.
- **Stop and ask:** before deleting or renaming anything in the store.

### `disk-low`
- **Means:** with `--min-free-mb MB`: the filesystem holding the state dir (`state: <n> MB free`) or the `--backups` dir (`backups: <n> MB free`) has less than MB megabytes available (rounded down to 50 MB), or its free space cannot be read (`free space unreadable`). Writes and backups fail once it is full. No path is printed.
- **Check first:** `df -h DIR` on that dir; on the Mac, free space in System Settings > General > Storage.
- **Next step:** free space only from files known to be safe to remove that are not Hass state, backups or owner files, then re-run the check.
- **Stop and ask:** before deleting anything owner-related; never delete or rotate backups to make room without the owner.

### `paused-long`
- **Means:** changes have been paused for longer than `--paused-hours` (default 24; `over <N> h`), or the pause time cannot be read (`unreadable time`). Every approved change is held until someone sends `resume changes`. The `paused` info line still shows when.
- **Check first:** ask the owner why changes are paused; the owner sends `status` to see the waiting drafts.
- **Next step:** the owner sends `resume changes` once the pause is no longer wanted; resuming never applies anything. Health never resumes by itself.
- **Stop and ask:** nobody knows why changes were paused, or the pause time is unreadable (tell the operator).

### `daily-limit`
- **Means:** with `interpreterDailyCap` set: `<n> message(s) not read today, cap <CAP>`. That many of the owner's messages on the current Pacific day got the daily-limit reply, so Michael's new change requests are refused until Pacific midnight. Status, commands and approvals still work. Only the count is shown: no message text, sender, chat or id. The `interpreter` info line shows today's calls.
- **Check first:** the `interpreter` info line (`<calls> of <CAP> today`); reaching the cap with no refused message raises nothing.
- **Next step:** tell Michael his change requests resume after midnight Pacific; do not replay messages or edit rows. The problem clears itself the next Pacific day.
- **Stop and ask:** before changing the cap: only G changes `interpreterDailyCap` (H22), never an operator workaround.

## Info lines

### `interpreter`
- **Means:** `<calls> of <CAP> today`, shown only when the private config sets `interpreterDailyCap`: how many interpreter calls were attempted on the current Pacific day (failed calls count too). Info only: reaching the cap alone is not a refusal; the problem `daily-limit` is raised only when a message was actually refused. A missing usage table or no row for today reads as 0.

### `backup-content`
- **Means:** with `--backups`: the newest complete backup within `--backup-hours` lists no `content.bundle` (`content restores from Git only`; made before FAV-07 or without a content commit). Info only: it never changes `ok`, `notify` or the exit code, and older backups never raise it; the next `python3 hass/statebackup.py create` with a readable writer HEAD clears it.

### `conversation`
- **Means:** `conversation.sqlite3` does not exist yet (`no conversation yet`). Normal before the first owner message.
- **Check first:** whether owner messages have already been answered.
- **Next step:** none when nothing has been exchanged yet.
- **Stop and ask:** it appears after messages were answered: the check is reading the wrong state dir (treat as `state`).

### `paused`
- **Means:** changes are paused since the time shown (chat `pause changes`, or a restore with `--paused`).
- **Check first:** the owner sends `status` to see the waiting drafts.
- **Next step:** the owner sends `resume changes` when the pause is no longer wanted; resuming never applies anything.
- **Stop and ask:** nobody knows why changes were paused.

### `photo-unused`
- **Means:** with `--writer`: the writer worktree has `assets/products/photo-<sha>.jpg|png` copies that no product's `image` uses (`<n> unused: <names>`, at most five names, then `and <m> more`), usually left by an undo or a newer photo. Info only: it never changes `ok`, `notify` or the exit code. File names only; no path is printed.
- **Check first:** `git -C WT log --oneline -- storefront-mockup/assets/products/FILE` to see which change added it, and that no product in `hass/content/products.json` names it.
- **Next step:** removing a file is an attended operator step: `git rm` it in the writer worktree on its branch, then commit. Health and Hass never delete it.
- **Stop and ask:** the owner undid that photo because it showed a person, a receipt or a private place (it stays in Git history; tell the operator).

The host checks below run with `--host-dir` (the HASS-SVC-1 health timer). They are read-only, never open the secret file and print no path, text or sender.

### `relay-stuck`
- **Means:** reply rows older than 15 min the Mac has not acknowledged (detail: count), or `relay.sqlite3` is a link, not a regular file or unreadable.
- **Check first:** `mac-silent`; `systemctl --user status hass-worker hass-receiver`. **Stop and ask:** the Mac is on but rows stay (tell the operator).

### `mac-silent`
- **Means:** the forwarder's last pull is over 10 min old (detail: 10-minute step, `over 2 h` past 2 h). Mac sleep, logout and reboot are unmeasured (H07).
- **Next step:** `over 2 h` is a Mac-physical fault: tell the operator (a G card). Shorter gaps only need watching.

### `release-open`
- **Means:** a release journal is not closed (`live`, `not-applied`, `reverted`, `closed`). Detail: the state(s) only: `not-published`, `unknown`, `unconfirmed`, or an in-progress state older than 15 min.
- **Stop and ask:** always (a G card). Do not publish by hand while a release is open; the next change is refused until it is settled.

### `release-books`
- **Means:** `publish.json` or a journal in `releases/` fails the PUBLISH-1 checks (missing, linked, wrong mode, damaged, out of order). Every release is refused.
- **Stop and ask:** always; G repairs the books or runs `publish_live.py adopt`.

### `live-unconfirmed`
- **Means:** a release journal is `unconfirmed` or `unknown` (detail: count): pushed, but the live site was not seen to match.
- **Check first:** the live site by eye. **Stop and ask:** always (a G card).

### `clover-token`
- **Means:** host.json has a `clover` block (HASS-CLOVER-2) and its token file is not usable, judged by lstat only: `missing`, `unreadable`, `not-regular`, `owner`, `mode`, `folder` or `size`.
- **Next step:** `python3 -B hass/host.py check --host HOST_JSON` shows the same word. Fix the file's or folder's mode or owner only. **Stop and ask:** never open, copy or print the token; G replaces it.

### `clover-sync`
- **Means:** the private till cache has had no good pull for over 2 hours (`last:` names the last result word: `unreachable`, `refused-key`, `rate-limited`, `token`, `clover-error`), or the cache is not private.
- **Next step:** `python3 -B hass/clover/cli.py status --host HOST_JSON`, then `systemctl --user status hass-clover-sync.timer`. `refused-key` means Clover refused the key: tell G, do not retry. The chat already tells Mike it can't reach the till.

### `host-config`
- **Means:** `host.json` is refused (mode, type, closed keys) or the secret file's lstat breaks D5: `missing`, `type`, `owner`, `mode` or `size`.
- **Next step:** `python3 hass/host.py check --host HOST_JSON` names the fields. **Stop and ask:** never copy or print the secret; G fixes it.

### `publishing-stopped`
- **Means:** info: the STOP file (`~/.config/hass/STOP`) exists, so no change goes live. The chat still answers.

### `stopped-long`
- **Means:** the STOP file has existed over 24 h. **Next step:** G removes it (`rm ~/.config/hass/STOP`) or leaves it on purpose.

### `alert-log`
- **Means:** `--alert-log` is a link, inside the repo or state dir, or not in an existing folder (exit 2); or (info) the line could not be written.

## Service and Mac behaviour

What is known comes from the sandbox user unit file and the Mac notes in IMPLEMENTATION.md; everything else is unmeasured and must not be assumed.

| Event | Known | Not yet measured | Shows up as |
| --- | --- | --- | --- |
| Agent Orange reboot | The sandbox unit is a user unit wanted by the default target, so it starts only when the user session (or lingering) starts it. | Whether lingering is on; how long the Hass services take to return. | `inbox-stuck`, `outbox-stuck` |
| Sandbox service crash | The unit has `Restart=on-failure` with a 3 second delay, so a crash is restarted by the service manager. | How often it has crashed in practice; whether a restart loop would be noticed. | no health check |
| Mac sleep | The Mac must stay powered, connected and signed in appropriately. | What the bridge does while asleep; the H07 compatibility check has not run. | `outbox-stuck` |
| Mac logout | The Mac must stay signed in appropriately. | What the bridge does after logout; the H07 compatibility check has not run. | `outbox-stuck` |
| Mac reboot | A reboot may need a person to unlock or sign in. | Whether it recovers without a person; the H07 compatibility check has not run. | `outbox-stuck` |
| macOS update | The Mac must stay powered and connected. | Whether the bridge survives an update; the H07 compatibility check has not run. | `outbox-stuck` |

## Restore

First pick the backup: `python3 hass/statebackup.py list --out BACKUPS` (read-only) names every `hass-state-*` entry, newest first; use one with `complete: true` (`no manifest (interrupted)` is an unfinished backup).
1. `python3 hass/statebackup.py verify BACKUP` must answer `ok`.
2. Drill only: `python3 hass/statebackup.py drill BACKUP --into NEWDIR --worktree DRILLWT` verifies, restores into a new state dir that starts with changes paused, runs the health check and the history on it and prints one JSON line (`ok`, or `drill-failed`/`corrupt`/`refused` with the `step`).
   DRILLWT is a separate drill worktree, never the writer worktree; the drill dir is left in place for inspection.
   Content: add `--content-into NEWCONTENT` to drill/restore; the site content and committed photos come back from the backup's bundle at `contentCommit`, never from the live checkout (detached, no remote; its own `hass/sitegen.py --check` must pass, else `contentCheck: failed` and drill `step: content`).
   Backups made before FAV-07 have no bundle; for them content comes from Git as before.
3. Fallback by hand: `python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused`, then `python3 hass/health.py --state NEWDIR` and `python3 hass/editor.py history --state NEWDIR`.
4. A live restore onto the writer worktree is an attended operator action; `statebackup.py` refuses it.

## H24 design visual check

Before a design change goes to same-thread review, the operator runs `python3 -B hass/design_preview.py --base REF --head REF --out DIR` from any folder inside the worktree. It captures evidence only: it sends nothing, merges nothing, publishes nothing and runs no incoming text. Looking at the PNGs and then asking for review in the same thread stays an attended operator step.
- **Scope first:** `hass/design_check.py` runs first. A change outside the design surface prints one `{"result": "outside", ...}` line and exits 1 with no folder made and no browser started.
- **What is compared:** the seven design files of each ref (read with read-only `git show` from the resolved commits) laid over the current worktree's other site files, so content, `community.js` and the photos are today's, not either ref's. It compares design surfaces, not whole historic sites. Nothing is checked out, written to the repository or the worktree, and neither ref's code is run.
- **Output:** `DIR` must be outside the repository and its Git folders, with no symlink on its path, and either new (made 0700) or an existing empty 0700 folder; otherwise exit 2 (`{"result": "usage"}`) and nothing is captured. Eight PNGs, all 0600: `base-home-phone.png`, `base-hike-phone.png`, `head-home-phone.png`, `head-hike-phone.png` (390 wide) and the same names with `-phone-desktop` (1280 wide). Delete `DIR` once reviewed; it is never sent or kept in private state.
- **Result:** one JSON line, `ok` (exit 0) or `preview-failed` (exit 1), with each capture's PNG paths (null when absent), its checks (`pageLoaded`, `noHorizontalOverflow`, `noPageErrors`, `noPosts`, and `desktop:` copies) and a short error. A failed phone check skips only that page's desktop capture; the other pages are still captured and partial PNGs are kept for inspection. A passing check is not design approval.
- **Setup:** needs Node and Playwright; set `PLAYWRIGHT_MODULE` (and `CHROMIUM_PATH` if Chromium is not found), as for the storefront QA scripts. The tests skip their browser cases without `PLAYWRIGHT_MODULE`.
