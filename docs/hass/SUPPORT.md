# Hass support path (H17/H19)

The operator runs `python3 hass/health.py --state DIR [--backups DIR] [--seen FILE]` on Agent Orange. It prints one JSON line;
exit 0 is ok, 1 means problems, 2 means unsafe (nothing else was checked). Each problem names a check id and a short detail
(counts or codes only). With `--seen FILE`, `notify` is true only when the set of problems changed.
The owner's first move is always the chat command `status`. The support contact and account ownership are recorded privately
by the owner/G (H22), never in Git. Read-only checks come first; anything that writes state happens only after `pause changes`.

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
- **Means:** with `--backups`: no complete `hass-state-*` backup within `--backup-hours`, no complete backup at all, or the backup dir is unreadable.
- **Check first:** `ls -l BACKUPS`; `python3 hass/statebackup.py verify BACKUP` on the newest one.
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
- **Check first:** re-run the check once.
- **Next step:** `pause changes` if the chat still answers; leave the file untouched. Backups do not hold the inbox, so there is nothing to restore.
- **Stop and ask:** always. Recreating the queue needs a new start point, which the owner/G decides.

### `writer`
- **Means:** with `--writer`: one entry per reason `apply` would refuse the recorded writer worktree: `uncommitted changes`, `branch main` or `detached HEAD` refused, `git user.name`/`user.email` not configured, `main checkout` refused, not the top of a Hass checkout (moved or deleted), or `config.json` missing (`not initialised`) or unreadable. Git runs read-only; no path is printed.
- **Check first:** `git -C WT status` and `git -C WT branch --show-current` on the worktree recorded in `config.json`.
- **Next step:** after `pause changes`, commit or stash in the writer worktree, switch it to a non-main branch, or set its Git identity; re-run the check, then the owner sends `resume changes`.
- **Stop and ask:** the worktree is gone or is the main checkout (re-running `python3 hass/editor.py init` onto a new linked worktree is attended), or changes there are not known.

### `model`
- **Means:** with `--model` (a loopback address only): the local model did not answer `/api/tags` within 3 s (`unreachable`), answered with an error status (`http <status>`), sent something that is not a model list (`bad reply`), or the `--model-name` model is missing (`model not installed`; a name without a tag means `:latest`). No URL or reply text is printed.
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

## Info lines

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

## Restore

First pick the backup: `python3 hass/statebackup.py list --out BACKUPS` (read-only) names every `hass-state-*` entry, newest first; use one with `complete: true` (`no manifest (interrupted)` is an unfinished backup).
1. `python3 hass/statebackup.py verify BACKUP` must answer `ok`.
2. Drill only: `python3 hass/statebackup.py drill BACKUP --into NEWDIR --worktree DRILLWT` verifies, restores into a new state dir that starts with changes paused, runs the health check and the history on it and prints one JSON line (`ok`, or `drill-failed`/`corrupt`/`refused` with the `step`).
   DRILLWT is a separate drill worktree, never the writer worktree; the drill dir is left in place for inspection.
3. Fallback by hand: `python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused`, then `python3 hass/health.py --state NEWDIR` and `python3 hass/editor.py history --state NEWDIR`.
4. A live restore onto the writer worktree is an attended operator action; `statebackup.py` refuses it.
