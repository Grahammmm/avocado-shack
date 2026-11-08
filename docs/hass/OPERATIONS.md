# Running Hass on AgentOrange (HASS-SVC-1)

Unit templates live in `deploy/hass/`. **Installing, enabling and starting them is G's runbook step, not code.** Nothing in the
repo installs a unit, starts a timer or restarts a service.

## What runs

| Unit | Does | Runs |
| --- | --- | --- |
| `hass-receiver.service` | `host.py serve`: sealed inbound and the reply relay | always |
| `hass-worker.service` | `host.py work`: drains the inbox, applies owner `yes`, queues replies | always |
| `hass-health.timer` / `.service` | `health.py` with `--host-dir` and `--alert-log` | every 5 min |
| `hass-backup.timer` / `.service` | `statebackup.py create` | 03:30 Pacific, `Persistent=true` |

All four use `%h` paths, `UMask=0077`, `NoNewPrivileges=true` and `PrivateTmp=true`; the long-running ones use
`Restart=on-failure`. No unit holds a secret (the key is a 0600 file read by the program).

The code runs from the **runtime worktree** `~/.local/share/hass/runtime`, detached at the reviewed runtime commit R. `host.py`
refuses to start when that checkout's HEAD is not `runtimeCommit` in `host.json`, or when it has uncommitted changes. The
**writer worktree** (`~/.local/share/hass/writer`, branch `hass/live`) holds content only. Moving to a newer R is attended: a new
detached runtime worktree, `runtimeCommit` updated, services restarted (HASS-SYNC-1 defines it).

## Pause

- **Michael:** `stop changes` or `pause changes` stops approvals from applying; `resume changes` lets them apply again (H17). The
  chat keeps answering.
- **G, publishing only:** `touch ~/.config/hass/STOP` stops all live publishing while the chat still answers. `rm
  ~/.config/hass/STOP` resumes. Health shows `publishing-stopped` (info) and, after 24 h, the problem `stopped-long`.
- **G, full stop:** `systemctl --user stop hass-worker hass-receiver`, then on the Mac `launchctl bootout` of the forwarder
  (runbook step 23).

## Alerts (H19 recommendation)

The timer runs `health.py` every 5 min. When the set of problems changes it appends one line to `~/agent-work/modes/ALERTS.log`:
`<UTC time> HASS-HEALTH <12 hex> <check ids>`. The line has ids only: no detail, text, sender or path. The same problem set does not
repeat. Exit 1 (problems) is not a failed unit; exit 2 (unsafe state, bad `--seen` or `--alert-log`) is.

| Check | Goes to |
| --- | --- |
| `mac-silent` with `over 2 h` | a G card, `G-REASON: hardware` |
| `release-open`, `release-books`, `live-unconfirmed` | a G card, `G-REASON: admin` |
| everything else (`relay-stuck`, `host-config`, `inbox-stuck`, `backup-age`, `stopped-long`, ...) | an ALERTS line only |

Each live publish is an info line, never a page. What to check for each id is in `SUPPORT.md`.

## Restore drill (unchanged)

1. `python3 hass/statebackup.py verify BACKUP`
2. `python3 hass/statebackup.py drill BACKUP --into NEWDIR --worktree DRILLWT`
3. By hand: `python3 hass/statebackup.py restore BACKUP --into NEWDIR --worktree DRILLWT --paused`, then
   `python3 hass/health.py --state NEWDIR`.

Backups are restored into a new directory; the live state is never overwritten.

## Live self-test (HASS-LIVE-AUDIT-1)

`scripts/hass/live_selftest.sh` checks the running system with synthetic data only and changes nothing: it restarts
nothing, sends nothing and opens no key. It runs the Mac forwarder, host server and worker code end to end in temp dirs
(status, a draft, reply retry without a duplicate, a stranger ignored, cancelled and expired codes doing nothing), then
reads the services, timers, `health.py`, `inbox.py status`, disk and journal growth. `--model NAME` adds a draft round
trip through the local model on three synthetic eval cases (a few minutes of CPU). One `PASS|WARN|FAIL` line per check
and a `HASS-SELFTEST` summary line; exit 1 when a check failed. Every read of a command or helper (git status and
rev-parse, each `systemctl` query, `health.py`, `inbox.py`, the report parser, `find`, `date`, `du`, `df`,
`journalctl`, the synthetic and model helpers) keeps its own exit status, and that status is checked before the output
is used: a read that exits non-zero shows `unknown` and fails even when it printed a good-looking value; it never reads
as clean, healthy, active, zero or "not run yet". A test table (`hass/tests/test_live_selftest.py`) checks each of
these reads that way. A nightly timer for it is proposed in
`reports/hass/hass-selftest.{service,timer}.candidate` and is not installed.

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

## Not measured yet

Mac sleep, logout, reboot and macOS update behaviour, and how long the services take to return after an AgentOrange reboot, are
**UNVERIFIED** until the H07 compatibility check has run. Until then `mac-silent` is the only sign of them.
