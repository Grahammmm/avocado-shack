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

### `backup-age`
- **Means:** with `--backups`: no complete `hass-state-*` backup within `--backup-hours`, no complete backup at all, or the backup dir is unreadable.
- **Check first:** `ls -l BACKUPS`; `python3 hass/statebackup.py verify BACKUP` on the newest one.
- **Next step:** `python3 hass/statebackup.py create --state DIR --out BACKUPS` (OUT mode 0700). It reads state only; `busy` means retry later, `unsettled` means `recover` first (after `pause changes`).
- **Stop and ask:** `create` answers `refused` (backups include `inbox.sqlite3`; a leftover `inbox.sqlite3-journal` is refused as an unknown entry) or `verify` answers `corrupt`, the disk is full, or a backup timer needs installing (attended).

### `seen`
- **Means:** `--seen FILE` is a symlink, lies inside the repository or the state dir, or its folder is missing. Exit 2; no other check ran.
- **Check first:** `ls -l` on the seen path and its folder.
- **Next step:** point `--seen` at a plain file in an existing folder outside both (a missing file is created on the next run).
- **Stop and ask:** the file turned into a symlink without a known reason.

### `inbox-stuck`
- **Means:** inbound messages have stayed pending in `<state>/inbox.sqlite3` longer than `--inbox-minutes`; the detail is the count. The drain is not running or one message keeps failing.
- **Check first:** the owner sends `status`; re-run the check to see whether the count moves.
- **Next step:** none in the repo: there is no drain command. Leave the queue as it is; pending messages are handed on in order once the drain runs.
- **Stop and ask:** before any service restart (attended), queue edit or deletion; when the count persists across two checks.

### `inbox-integrity`
- **Means:** `inbox.sqlite3` fails its quick check (`<n> issue(s)`) or cannot be opened (`database unreadable`).
- **Check first:** re-run the check once.
- **Next step:** `pause changes` if the chat still answers; leave the file untouched. Backups do not hold the inbox, so there is nothing to restore.
- **Stop and ask:** always. Recreating the queue needs a new start point, which the owner/G decides.

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

1. `python3 hass/statebackup.py verify BACKUP` must answer `ok`.
2. Drill only: `python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused` builds a new state dir that
   starts with changes paused; DRILLWT is a separate drill worktree, never the writer worktree.
3. Check the drill with `python3 hass/health.py --state NEWDIR` and `python3 hass/editor.py history --state NEWDIR`.
4. A live restore onto the writer worktree is an attended operator action; `statebackup.py` refuses it.
