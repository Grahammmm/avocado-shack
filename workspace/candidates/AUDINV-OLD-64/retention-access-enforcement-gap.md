# Retention and access enforcement gap — AUDINV-OLD-64

CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED. Overall: UNVERIFIED/HOLD.

Inspected main: `b302d26bee6a4d8993f9da324d743bf206c56aca`. Source capture: 2026-11-16T03:39:16.821759+00:00.

## Recorded decisions, not model-supplied owner acceptance

- 2026-11-06T00:00:00-08:00: Date only (midnight placeholder, not measured approval time): G approved use of recommended H21 answers once the spec lists them. This is not observed enforcement or undated owner acceptance. [g1606]
- 2026-11-15T00:00:00-08:00: Date only (midnight placeholder): audit-row work approved; retire/delete HOLD and other explicit holds retained. This report is not deletion authority. [g1931]

Actual policy agreement and acceptance remain with the owner. No owner contact occurred.

## Class-by-class comparison

Counts, configured periods, implemented code, installed/enabled mechanisms and observed enforcement are separate layers.
SOURCE means inspected code/documentation, not installed operation. HISTORICAL is a dated prior receipt, not current measurement.
UNKNOWN is missing evidence, never a measured zero. All current configured/installed/observed layers are UNKNOWN.

| Data class | Policy basis / period | Mechanism / receipt | Layers | Measured scope / date | Access boundary | Missing evidence | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| inbox-payloads | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: erased when handled | Inbox._mark sets payload NULL on completion; history never stores payload. Code is not erasure observation. [operations, g1606, inbox, memory, backup-doc] | counts=NOT-COUNTED; configured=UNKNOWN; code=SOURCE; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Private state design: 0700 directories / 0600 databases; current permissions, principals and ACLs UNKNOWN | Current completion-to-payload-clear receipt; pending/retry exclusions; backup copies and SQLite residual-byte treatment | UNVERIFIED/HOLD |
| inbox-ids | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 90 days | Read-only retention counts by received_at; completed IDs retained for dedup; no 90-day purge established. [operations, g1606, retention, backup-doc] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Private state design: 0700 directories / 0600 databases; current permissions, principals and ACLs UNKNOWN | Dated ID-expiry enforcement receipt and dedup/replay boundary; nonces/start point have separate semantics | UNVERIFIED/HOLD |
| mac-spool | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 7 days after delivery | Forwarder spool stores payload/state/done_at and sent metadata; inspected source does not establish 7-day retention enforcement. [operations, g1606, forwarder] | counts=NOT-COUNTED; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Mac spool owned private design; effective Mac user/file permissions and transport access UNKNOWN | Delivered-row pruning receipt at 7 days, pending protection and installation/version mapping | UNVERIFIED/HOLD |
| relay-rows | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 30 days after ack | RelayStore.ack records acked_at but deletes picture metadata only, not relay rows. Ack delivery is not row retention enforcement. [operations, g1606, relay, memory, live-audit] | counts=NOT-COUNTED; configured=UNKNOWN; code=SOURCE; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | RelayStore uses memory.private_db (0600); effective host/peer ACLs UNKNOWN | 30-day relay-row purge receipt; current install and acknowledged-row age distribution | UNVERIFIED/HOLD |
| relay-pictures | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: picture bytes cleared at ack; picture metadata cleanup after 30 days | RelayStore.ack sets picture.data NULL and removes old acknowledged picture rows. No secure/global erasure claim. [operations, g1606, relay, live-audit] | counts=NOT-COUNTED; configured=UNKNOWN; code=SOURCE; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Private relay database; authenticated transport intended; actual current peer boundary UNKNOWN | Observed per-picture clearing receipt and copied screenshot/backup scope; metadata cleanup only runs when ack is called | UNVERIFIED/HOLD |
| screenshots | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 90 days | Read-only PNG count uses file mtime; no 90-day deletion enforcement receipt. [operations, g1606, retention, options] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Private state design: 0700 directories / 0600 databases; current permissions, principals and ACLs UNKNOWN | Dated screenshot expiry receipt; unsent/open proposal protection; relay and backup copies | UNVERIFIED/HOLD |
| conversation-outbox | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 1 year | Read-only counts use received_at for messages and created_at for outbox; count is not erasure. [operations, g1606, retention, conversation, memory, live-audit] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Owner-channel filter code; private database design. Historical 2026-11-07 H08 partly live on G phone, not current owner/ACL acceptance | One-year coordinated message/outbox retention receipt; unsent and dedup exclusions; actual access review | UNVERIFIED/HOLD |
| approval-change-release | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 2 years | Read-only approval count exists; separate change files, audit logs and release journals are not a coordinated counted/purged set. [operations, g1606, retention, options, backup-doc] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Private state design: 0700 directories / 0600 databases; current permissions, principals and ACLs UNKNOWN | Per-store 2-year enforcement receipts, audit continuity and undo protection; change/release coverage missing | UNVERIFIED/HOLD |
| photo-originals | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 1 year after last use | Retention report ages by sidecar received_at, NOT last use: age-basis conflict. Private web copies have separate coverage. [operations, g1606, retention, media, options] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Media private-root and no-symlink code; originals may contain metadata; actual access and last-use inventory UNKNOWN | Last-use basis agreement/evidence; expiry receipt; undated/orphan decisions and backup/Git/phone copy coverage | UNVERIFIED/HOLD |
| backups | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: 30 daily | Report counts timestamp-named backup folders; configured scheduling or folder count is not verified rotation. Historical 2026-11-07 backup timer had not run. [operations, g1606, retention, backup-doc, live-audit] | counts=SOURCE; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Backup design enforces private output/manifest modes; effective access, encryption and off-box scope UNKNOWN | Current 30-daily rotation receipt plus verified recovery window; deletion remains held | UNVERIFIED/HOLD |
| mac-messages | H21 recorded proposal; dated recommendation approval conditional, owner agreement unverified: Keep messages: 1 Year | Mac runbook proposes UI setting, explicitly UNVERIFIED until attended step 18; not a setting read or expiry measurement. [operations, g1606, mac-runbook, options] | counts=NOT-COUNTED; configured=UNKNOWN; code=UNKNOWN; installed=UNKNOWN; observed=UNKNOWN | Current live scope/date UNKNOWN; source inspection 2026-11-16T03:39:16.821759+00:00; historical H21 audit 2026-11-07 only | Mac Messages account/device/provider access UNKNOWN; no account or device inspection | Sanitized dated actual setting and observed device/provider expiry coverage; owner phone copies independent | UNVERIFIED/HOLD |

Totals: 11 classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0.

## Evidence limits and stop boundary

- This is source inspection plus reused sanitized historical receipts, not a current transport/storage measurement. No live store, credential, config, service or Mac was read.
- HASS-RETAIN-1 is referenced as later enforcement in OPERATIONS.md:86 and as planned work in HASS-LIVE-AUDIT-1:271; a reference is not a completion receipt.
- The 2026-11-07 H21 receipt says retention periods not decided/nothing deletes. Preserve its date and scope: inbox/relay partial clearing code exists, so that historical shorthand is not proof of universal absence of clearing.
- RETENTION-OPTIONS.md and HANDOVER.md still leave owner decisions open; comparison periods 7/30/90 days are not selected defaults. They do not silently supersede the dated G recommendation approval.
- Configured periods are UNKNOWN here, not read from host configuration. Implemented clearing, installed/enabled mechanisms and observed enforcement remain distinct.
- Photo last-use versus received-at and relay-row versus picture-metadata coverage conflicts remain HOLD; missing evidence is not zero retained items.
- Read-only counts do not prove expiry. SQL NULL is not proof of erasure from SQLite free pages, backups, Git, Messages, provider or device copies. No legal/compliance/global-erasure conclusion is supplied.
- Existing historical audit locator reports/AUDIT-AVOCADO-HASS-2026-11-01.md:99 is inventory context; that path is absent from inspected repo main, so no current digest or independent receipt is invented.
- Decision locators are operator-local sanitized excerpts; digests bind retained excerpt bytes, not the whole log. Repo-source digests bind full inspected files; capture time is not enforcement time.
- No live enforcement, owner contact, access/credential change, send, restart or deletion occurred. Actual policy agreement and acceptance remain with the owner; missing facts remain with existing custodians. Stop after this report.
- Mechanical validation is REVIEW_REQUIRED, not semantic acceptance or permission to install/apply. No ongoing framework or production CI registry is changed.

## Immutable sanitized sources

### operations
`docs/hass/OPERATIONS.md`; SHA-256 `61f9f382a963c0b6dffd958a8aeeb97bb5a45d58a9c12b087d48173a4f860a5f`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 3-5:
```text
Unit templates live in `deploy/hass/`. **Installing and enabling them is G's runbook step, not code.** Nothing runs automatically.
The explicitly attended [runtime release tool](RUNTIME-RELEASE.md) can stop/start the three existing runtime units only;
it never installs/enables units or changes their definitions. Workers must not run its apply command.
```
Lines 16-17:
```text
All four use `%h` paths, `UMask=0077`, `NoNewPrivileges=true` and `PrivateTmp=true`; the long-running ones use
`Restart=on-failure`. After 5 failed starts in 5 minutes (`StartLimitIntervalSec=300`, `StartLimitBurst=5`) the receiver or worker stays `failed` instead of looping: fix the cause, then `systemctl --user reset-failed <unit>` and start it (operator step). No unit holds a secret (the key is a 0600 file read by the program).
```
Lines 71-86:
```text
## Retention proposal (H21, G decides; nothing enforces it yet)

| Data | Proposed period |
| --- | --- |
| Inbox payloads | erased when handled (already) |
| Inbox ids and times | 90 days |
| Mac spool | 7 days after delivery |
| Relay rows | 30 days after ack (picture bytes cleared at ack) |
| Proposal and result screenshots | 90 days |
| Conversation messages and outbox | 1 year |
| Approvals, change records, release journals | 2 years (the audit trail of live changes) |
| Photo originals | 1 year after last use |
| State backups | 30 daily |
| Messages app on the Mac | "Keep messages: 1 Year" |

Enforcement is a later unit (HASS-RETAIN-1). `python3 hass/retention.py report --days N` measures it and deletes nothing.
```
### options
`docs/hass/RETENTION-OPTIONS.md`; SHA-256 `bc7a4acf179cec7d093dda3058cd8306d1b06c401e11e62806de229d214a1136`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 1-16:
```text
# How long to keep private data (H21) - options and questions

**Open decision for Michael and G. This page records no decision, selects no period, deletes nothing and authorizes no cleanup.** 7, 30 and 90 days are three comparison points, not chosen defaults and not limits that anything enforces. The row stays open in [HANDOVER.md](HANDOVER.md) and in [FEATURES.md line 49](FEATURES.md#L49) ("Needs G: owner retention periods; no deletion step enforces them yet") until Michael and G answer privately.

The page shows, for each kind of private data the retention report counts, what it holds, what reads it today and what would stop working if it were later deleted after 7, 30 or 90 days. It names kinds of field only, never examples, and it contains no private value, id, contact, message, photo or state path. Product source paths and field names are allowed.

## What the retention report is

`python3 hass/retention.py report --state DIR --days N` ([retention.py](../../hass/retention.py), owner action 4 at [line 11](../../hass/retention.py#L11)) is a read-only count. It opens the databases read-only, creates and writes nothing, and always prints `deletes: 0`. No deletion step enforces a retention period on any class it counts. N is a whole number from 1 to 36500.

- **Cutoff.** A row or file counts when it is strictly older than the report time minus N elapsed days. This is a count of 24-hour days, not a Pacific calendar-day policy.
- **What each class is dated by.** Inbox and message rows: the time the message was received. Outbox and draft rows: the time the row was created. Approvals: the approval time. Closed memory rows: the time it was forgotten, else the time it was replaced. Screenshots: the file's last-changed time. Photo originals: the receipt time in the small description file beside each original. Backups: the UTC time in the backup folder's name. A web copy is counted through its original's date.
- **`oldest`** is the oldest dated item the report found, not the oldest item past the cutoff, so it can be younger or older than N days and does not say that anything is overdue. Drafts print no `oldest`; they print an open count and a closed count.
- **Open and closed drafts.** "Open" means the draft can still change state, so it includes drafts waiting for a yes, waiting for details, approved, applied and checked (an applied or checked change can still be undone). "Closed" means rejected, expired, failed or undone. An open draft can be old; age alone never makes open work safe to remove.
- **Times that cannot be read.** A missing, zone-less or malformed time counts nowhere, and a backup name that is not a real calendar time is ignored. Some message rows are stored with no receipt time at all and are never aged. Photo originals whose description file has no usable time are counted as `undated`, and web copies whose original is gone are counted as `webOrphans`. Neither is ever given a guessed age, and each needs its own decision.
- **Absent is not zero.** The photo folder and the backup folder are optional arguments. When one is not given its entry is empty, which is not a count of zero. When a store cannot be read its entry says `unavailable` and the report exits 1. A backup counted as complete has a finished manifest; that is not a verified restore point, which needs `statebackup.py verify`.
```
Lines 35-51:
```text
## Stores the report does not count

Anything below would need its own look, field list and decision before any cleanup. This page did not assess their readers beyond what is stated.

- **The audit log files** (one file per UTC day, ids and codes only, no message text): the first thing `history` reads. They are part of every backup ([audit.py](../../hass/audit.py)).
- **The editor draft and change files** described in the Drafts row.
- **Other tables in the two databases:** the chat each message came from, open requests (the owner's recent words while a question is open), the interpreter call log, usage counts, the pause marker, picture retries, the backlog notes, and the inbox start point and nonces.
- **The reply relay file** that the health check reads for unacknowledged replies.
- **Git history and the committed site photos** in the writer worktree, and the site content bundle inside each backup.

## Limits when data sits in more than one place

- Deleting one table or file on its own can leave dangling references (a row that names a picture that is gone, a history line with no draft behind it), weaken duplicate protection or make a restore inconsistent. Neither the retention report nor this page coordinates a cleanup across stores.
- Backups keep copies of what the current state no longer holds. Removing or forgetting something in the current state does not remove it from older backups.
- Committed photos and Git history, the owner's phone, the messaging provider and the language model host may hold their own copies. Deleting private cache does not erase those, and nothing here is a claim of global erasure or of meeting any legal or compliance standard.
- The backup lists photo originals and their description files only. When a media folder is given, a backup is refused if that folder holds a web-copy folder beside the originals ([statebackup.py](../../hass/statebackup.py)). How private web copies and the backup fit together is an open operator question.
- Support rules apply to any later cleanup: pause changes first, stop and ask before deleting or editing a database or a backup, never delete or rotate backups to make room without the owner, and run restores only into an isolated drill folder ([SUPPORT.md](SUPPORT.md#disk-low), [restore steps](SUPPORT.md#restore)). This page gives no deletion command, query, timer or live-state recipe.
```
Lines 57-71:
```text
## Questions Michael and G must answer

All of these are unanswered. Answers stay private and are never written into Git.

1. **Which period for which class?** Is the answer one period for everything or different periods for the classes above, and counted from what event (receipt, approval, close, backup time)?
2. **What is protected whatever the age?** How are waiting inbox rows, unsent replies, open drafts (including applied and checked changes that can be undone) and current memory kept out of any cleanup?
3. **How far back must undo, history and the audit log reach?** Is a change that is a month or a quarter old still expected to be undoable, and how far back should `history` and `status` reach?
4. **How long must the trial review be able to look back?** Does the retention period have to outlast the agreed trial, including the longest review range of 31 days?
5. **Originals versus reusable and site copies.** Are private photo originals kept longer, shorter or the same as private web copies, and what happens to photos already committed to the site?
6. **Undated and stray items.** What happens to originals with no usable receipt time, and to web copies with no original? Neither is ever given a guessed age.
7. **Backups.** How often are backups made, how long is the recovery window, how many verified recovery points are kept, and when is an older backup removed so that something removed from current state does not live on in it?
8. **Other copies.** How is a later authorized cleanup handled for backups and for the other copies named above?
9. **Who is responsible?** Who approves a cleanup, who has access to the private data, who runs it, and who handles an incident if it goes wrong?

Nothing on this page is a policy, a default, a sign-off or a decision date.
```
### retention
`hass/retention.py`; SHA-256 `78afe7ccad5627727f5e439435d51cfc43136c0394b242c6ed608d8830961d88`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 1-14:
```text
"""Hass retention report (H21, read-only): how much kept data is older than --days N. Deletes nothing.

    python3 hass/retention.py report --state DIR --days N [--media ROOT] [--backups DIR] [--now ISO]  (N: 1-36500)

One JSON line: per data class, the count strictly older than now - N days and the oldest kept UTC date (or null), dated
by inbox/messages received_at, outbox/drafts created_at (closed draft: no further transition), screenshot mtime, the
photo sidecar received_at (none usable: undated, never guessed), the backup name's stamp (other names ignored),
approvals approved_at and closed memory rows by forgotten_at, else superseded_at (active memory is not counted).
webOrphans: web copies whose original is gone (counted, never dated).
Zone-less or malformed times, and backup stamps that are no real calendar time, count nowhere. No ids, text or file
names print. SQLite opens mode=ro; nothing is created or written; the owner picks the period (owner action 4). Exit 1:
a store is missing or unreadable (its keys say "unavailable"); exit 2, before anything opens: bad usage (incl. a
--days reaching before year 1 from --now), a missing dir, a dir that is or sits below a symlink, or a symlinked or
non-regular database; else 0.
```
Lines 48-52:
```text
def _rows(path: Path, queries: dict) -> dict:
    """{name: rows} over one read-only connection; a missing table gives no rows. Raises sqlite3.DatabaseError."""
    with contextlib.closing(sqlite3.connect(f"{path.absolute().as_uri()}?mode=ro", uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        return {name: db.execute(sql).fetchall() if table in tables else [] for name, (table, sql) in queries.items()}
```
Lines 153-160:
```text
    for key, folder, scan in (("screenshots", sdir / "screenshots", _shots), ("media", mroot, _media),
                              ("backups", bdir, _backups)):
        try: doc[key] = None if folder is None else scan(folder, cutoff)
        except OSError: doc[key] = UNAVAILABLE
    try: doc["webOrphans"] = None if mroot is None else _web_orphans(mroot)
    except OSError: doc["webOrphans"] = UNAVAILABLE
    doc["deletes"] = 0
    return doc
```
### inbox
`hass/inbox.py`; SHA-256 `bd814288f7bf6339ccf2273250bb70e9e5599bd2eebe7fc77025112e010de95a`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 167-175:
```text
    def _mark(self, provider_id: str, disposition: str) -> None:
        with self._tx():
            self.db.execute("UPDATE inbound SET state = 'done', disposition = ?, done_at = ?, payload = NULL"
                            " WHERE provider_id = ? AND state = 'pending'",
                            (disposition, _iso(self.clock()), provider_id))

    def drain(self, conversation) -> list:
        """Hand each pending message to conversation.handle in order, marking it done afterwards. An exception from
        handle (or the mark) propagates and leaves that message and every later one pending for the next drain;
```
### relay
`hass/relay.py`; SHA-256 `01b9fba322525c2ff040643d030974dcc4f833fc7d050358d2130e8515ecd529`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 128-131:
```text
class RelayStore:
    """relay.sqlite3 in the host dir (0600): replies waiting for the Mac to pull and acknowledge them."""
    def __init__(self, host_dir):
        self.db = sqlite3.connect(memory.private_db(host_dir, "relay.sqlite3"), isolation_level=None, timeout=30)
```
Lines 182-189:
```text
    def ack(self, ids, now) -> int:
        """Idempotent; unknown ids are ignored. Returns how many rows this call newly acknowledged."""
        n = 0
        for i in ids:
            n += self.db.execute("UPDATE relay SET acked_at = ? WHERE id = ? AND acked_at IS NULL", (int(now), i)).rowcount
            self.db.execute("UPDATE picture SET data = NULL WHERE relay_id = ?", (i,))
        self.db.execute("DELETE FROM picture WHERE relay_id IN (SELECT id FROM relay WHERE acked_at < ?)", (int(now) - 30 * 86400,))
        return n
```
### media
`hass/media.py`; SHA-256 `a14b677004c07a567d68f2ddf6b3074a2acd9df871b003eac8bc0307581a6b0a`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 92-104:
```text
def _private_dir(path: Path) -> None:
    try: os.mkdir(path, 0o700)
    except FileExistsError: pass
    if not stat.S_ISDIR(os.lstat(path).st_mode): raise Refused("corrupt-store")

def _existing(path: Path):
    """None if nothing is at path; the bytes of a regular file; Refused for any other entry (symlink included)."""
    try: st = os.lstat(path)
    except FileNotFoundError: return None
    if not stat.S_ISREG(st.st_mode): raise Refused("corrupt-store")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)  # a FIFO swapped in after lstat never blocks open
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise Refused("corrupt-store")
```
### memory
`hass/memory.py`; SHA-256 `127abdac443b9b6d1fb640812b527bd922a0c8f90a0c2e7b0bb3f0bf77a90276`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 55-68:
```text
def private_db(sdir, name) -> Path:
    path = sdir / name
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENXIO, errno.EISDIR): raise editor_mod.UnsafeState(
            f"{name} must be a regular file, not a link") from exc
        raise
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode): raise editor_mod.UnsafeState(f"{name} must be a regular file, not a link")
        os.fchmod(fd, 0o600)
    finally: os.close(fd)
    # SQLite reopens by path; the intervening window is accepted for the owned 0700 state dir.
    return path
```
### conversation
`hass/conversation.py`; SHA-256 `7f1de0dc7a7519badf0390962c49c31ca292402735daefcaaf0a64ec667e60a1`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 831-838:
```text
    def handle(self, msg: Inbound, last_try=False, apply=True, forwarded_at=None) -> str:
        self._answering, self._forwarded = msg.received_at, forwarded_at
        self._to = msg.chat if self._is_owner(msg) else None
        self._asker = sender_key(msg.sender)
        self.outbox.msg_id, self.outbox.emoji_ok = msg.provider_id, voice.has_emoji(msg.text)
        try: return self._handle_message(msg, last_try, apply)
        finally:
            self._answering, self._forwarded, self._to, self._asker, self.outbox.msg_id, self.outbox.emoji_ok = None, None, None, None, None, False
```
### forwarder
`mac/hass_forwarder.py`; SHA-256 `8a381d62f79c070e0f451129daaef28345de9fa51bb9c0388546eb503b594606`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 136-160:
```text
class Spool:
    def __init__(self, directory, now, ready=False):
        """ready=True: the file and its tables already exist (an ack worker's own connection): no schema or meta writes."""
        self.clock = time.time
        self.directory = directory
        path = Path(directory) / "spool.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o177: raise ValueError("spool-file")
        finally: os.close(fd)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.stage = stagelog.off  # HASS-FAST-1: the Forwarder swaps in a StageLog
        if ready: return
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS inbound(provider_id TEXT PRIMARY KEY,payload TEXT,state TEXT,tries INTEGER,"
            "next_try_at REAL,created_at REAL,done_at REAL);"
            "CREATE TABLE IF NOT EXISTS fetch(guid TEXT,event TEXT,created_at REAL,tries INTEGER DEFAULT 0,next_try_at REAL DEFAULT 0,PRIMARY KEY(guid,event));"
            "CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY,value REAL);"
            "CREATE TABLE IF NOT EXISTS sent(reply_id INTEGER PRIMARY KEY,sent_at REAL);"
            "CREATE TABLE IF NOT EXISTS sent_pics(reply_id INTEGER,idx INTEGER,sent_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS pic_tries(reply_id INTEGER,idx INTEGER,tries INTEGER,next_try_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY,seen_at REAL);"
            "CREATE TABLE IF NOT EXISTS drops(reason TEXT PRIMARY KEY,count INTEGER);"
            "CREATE TABLE IF NOT EXISTS ack(provider_id TEXT PRIMARY KEY,state TEXT,created_at REAL,done_at REAL);"
```
### backup-doc
`hass/README.md`; SHA-256 `1073680cd7fff20b9ba8e41d3f6d0a88a04649578d9990a612d255cb69e2f469`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 179-185:
```text
- `create` writes `<out>/hass-state-<UTC stamp>/`: `config.json`, `drafts/`, `changes/`, `screenshots/`, `audit/` (the AVB-10 audit log; 0600/0700), SQLite online-backup snapshots of `inbox.sqlite3` (the H16 queue, when present; taken first) and then `conversation.sqlite3`, and `MANIFEST.json` (SHA-256 per file) last; `writer.lock` is never copied. Refused: `out` missing, not 0700, or inside the state dir, the repository or the writer worktree (exit 2); a symlinked or odd `config.json`/`writer.lock` before either is opened, any symlink or unknown entry (`refused`, each named); a held writer lock (`busy`); a pending journal (`unsettled`, run `editor.py recover` first); an existing backup dir of the same stamp (`exists`).
- `create` builds in a dot-named `.hass-state-<stamp>.partial-<pid>` folder and renames it to `hass-state-<stamp>` only after `MANIFEST.json` is written, so a failed run leaves no `hass-state-*` folder and the stamp stays free.
- `verify` checks the manifest layout, every hash and mode, unlisted files and symlinks and `PRAGMA integrity_check`; damage gives `corrupt` naming the file.
- `restore` verifies first, refuses an existing `--into` (left untouched), the recorded writer worktree (an attended operation) and a worktree that fails the editor checks, builds the new state dir beside `--into` and renames it into place. Only `config.json` `worktree` is rewritten.
- `drill` prints check ids and counts only (`ok`, `corrupt` with `step: verify`, or `drill-failed` with its step, keeping the restored dir); it never restores onto the writer worktree.

No network, no Git writes, no deletion of source data. Limits: drill on isolated copies only; no live restore, scheduling, retention, off-box copy or encryption.
```
Lines 198-204:
```text
`hass/inbox.py` `Inbox(state_dir, start_at=None)` keeps `<state>/inbox.sqlite3` (0600) next to the conversation store. Every inbound message is written there before any processing; nothing is backfilled as a command.

- **Start point.** The first open must pass `start_at` (timezone-aware ISO-8601) and records it; later opens reuse it, and a different value raises `start point already recorded as <iso>`. The module never moves it.
- `enqueue(msg)` → `queued`, `duplicate` (id already stored, nothing changes) or `history` (received before the start point; only id and time are kept, it never becomes a command). A `received_at` that is empty, has no zone or is not a date raises `ValueError` and stores nothing.
- `drain(conversation)` hands pending messages to `Conversation.handle` in `(received_at, provider_id)` order and marks each `done` with its disposition only afterwards. A crash in between re-delivers the message and `Conversation` answers `duplicate` without a second write; an exception stops the drain and leaves that message and later ones pending.
- Payloads are erased once a message is done (history rows never store one); retention periods stay H21.
- `seen()` is the persistent nonce set for the bridge envelope (`bridge.unseal(..., seen=inbox.seen())`), so a replayed envelope is refused after a restart; nonces older than one day are pruned when a new one is recorded.
```
### live-audit
`reports/hass/HASS-LIVE-AUDIT-1.md`; SHA-256 `37605ccf4ce18eb1aefe317a296b2d763910f5b1c8fd537001ff8bcc44b79c0d`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 3-3:
```text
Date: 2026-11-07, 14:35-14:50 PST, on AgentOrange. Author: opus-coder (card t_d5a579b9).
```
Lines 102-102:
```text
| H08 | Owner-only text channel | pass (43) | WORKS-LIVE (partly) | Owner chat and echo guard live (L1 `echo: 6`). Stranger, group and duplicate delivery never exercised live (no `ignored` disposition); synthetic PASS. |
```
Lines 114-115:
```text
| H20 | Backups and recovery | pass (25) | NOT-RUN | Backup timer never ran; `backups/` empty (L3 `backup-age`, L4). Restore drill fixtures only. |
| H21 | Privacy, retention, access | pass (9) | TESTED-ONLY | Logs carry counts and class names only (checked in L4 journal). Retention periods not decided; nothing deletes. |
```
Lines 271-271:
```text
| 18 | Retention: decide periods (OPERATIONS.md proposal) and build HASS-RETAIN-1 | safety | M | medium (deletion) | G (periods), then operator |
```
### mac-runbook
`docs/hass/MAC_RUNBOOK.md`; SHA-256 `b1ba7b5ecf8a7f2736628da96d4049431827850e1bfe2351cf917ad864a5cf21`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 17-18:
```text
3. **G / Mac:** Run `sudo pmset -a sleep 0 disksleep 0 autorestart 1`; the display may sleep. Set Messages → Keep messages: 1 Year (UNVERIFIED until step 18), H21.
   Expected: Mac stays awake and restarts after power loss; message retention is one year.
```
### handover
`docs/hass/HANDOVER.md`; SHA-256 `f006062750c0a845e3fc742fa080b2670891a29648f75bca3407d41e8f805c2f`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 27-27:
```text
| H21 | Message and media retention periods | Owner / G | [FEATURES.md line 49](FEATURES.md#L49), [Retention options](RETENTION-OPTIONS.md) |
```
### features
`docs/hass/FEATURES.md`; SHA-256 `41c6edb7f5c22a70772fba88ea943829544ae93305e1d15ea771d6a8c1ae67d5`; captured 2026-11-16T03:39:16.821759+00:00; repo-source.
Lines 49-49:
```text
| H21 | Privacy, retention and access | H18 | Owner-approved sender list, message/media retention and deletion rules are enforced; credentials and participant/message data stay out of Git, screenshots and routine logs. | Needs G: owner retention periods; no deletion step enforces them yet |
```
### g1606
`operator-local/decisions/G-DECISIONS.log:L1606 (sanitized excerpt)`; SHA-256 `26bfb1ad5dfd8ad9028efc8884c43e65922b17deaffb9557c8867b20f6e0f100`; captured 2026-11-16T03:39:16.821759+00:00; decision-excerpt.
Lines 1606-1606:
```text
2026-11-06 G: (3) Hass: use the recommended answers for H07/H19/H21/H22/H25 once the spec lists them;
```
### g1931
`operator-local/decisions/G-DECISIONS.log:L1931 (sanitized excerpt)`; SHA-256 `dff9c8226bc077113d8e2da5a890808a9e5ee0cd300df7a08be49a347f8bedf0`; captured 2026-11-16T03:39:16.821759+00:00; decision-excerpt.
Lines 1931-1931:
```text
2026-11-15 G: approve ALL 295 NOT-STARTED audit rows (7 review files); NEEDS-G groups: signing HOLD till trust anchor; retire/delete HOLD; publish/launch: approve 45-unit approve/deny draft pass only (UNITS45-DECIDE-1); setup: show each as card
```

## Actual local acceptance receipt

```console
$ python3 workspace/candidates/AUDINV-OLD-64/candidate.py --self-test
SELF-TEST PASS: 6 named synthetic tests (local-only)
exit: 0
$ python3 workspace/candidates/AUDINV-OLD-64/candidate.py --check retention-access-enforcement-gap.md --sources SOURCES.json
CHECK PASS: 11 classes; 11 UNVERIFIED/HOLD; observed enforcement receipts: 0
exit: 0
```
