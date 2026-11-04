# Release and handover (H25)

**Checklist only. No step below has been signed off; each decision is still open until its owner records it.**

This page lists what has to happen before Michael gets Hass and which decisions are still open and whose they are. It records no decision and does not say any step has happened. The scope of H25 is [FEATURES.md row H25](FEATURES.md#L53).

## Release steps

Run the steps in order. Each step names who does it. None of them is a service, timer or channel step.

1. **Standing acceptance run (operator).** From the repo root run `python3 hass/acceptance.py`. It prints one line per feature id and a last summary line. Every covered id must read `pass`. Ids reported as `not covered` have no automated check yet and stay open; the run does not turn them into passes.
2. **Restore drill (attended operator).** On an isolated backup, run the drill command copied from [`hass/README.md` line 172](../../hass/README.md#L172), with `BACKUP`, `DIR` and `WT` replaced by isolated paths of your own:
   `python3 hass/statebackup.py drill BACKUP --into DIR --worktree WT`
   The drill never restores onto the writer worktree. The command list and its limits are in [`hass/README.md` from line 163](../../hass/README.md#L163).
3. **Hand over the guides (G or the operator, in person).** Give Michael [PHONE_GUIDE.md](PHONE_GUIDE.md) and [LIMITS.md](LIMITS.md). The support path stays in [SUPPORT.md](SUPPORT.md).
4. **Owner trial (H18).** The trial plan is not in the repo yet, so follow the acceptance column of [FEATURES.md row H18](FEATURES.md#L41): Michael tries each listed task on his own phone. Link a `TRIAL.md` here once one exists.
5. **Private launch only.** A public site needs separate authorization and configured form and privacy behavior ([FEATURES.md row H25](FEATURES.md#L53)).

## Open decisions

Each row stays open until its owner records an answer. Source links go to the row at the base of this page; the line numbers move if the file changes.

| Id | Decision | Whose | Source |
| --- | --- | --- | --- |
| H07 | Which Mac and which Apple account run the bridge | Owner / G | [FEATURES.md line 25](FEATURES.md#L25) |
| H19 | How the service and its health checks run on the Mac and Agent Orange, and where alerts go | Operator / G | [FEATURES.md line 47](FEATURES.md#L47) |
| H21 | Message and media retention periods | Owner / G | [FEATURES.md line 49](FEATURES.md#L49) |
| H22 | Usage and spending limit; support, recovery and account record kept privately | Owner / G | [FEATURES.md line 50](FEATURES.md#L50), [SUPPORT.md line 7](SUPPORT.md#L7) |
| H23 | Which action types, if any, Michael opts into | Michael | [FEATURES.md line 51](FEATURES.md#L51) |

## Not in this page

- No decision, limit, period, account or contact is written here. Those are recorded privately by their owners, never in Git.
- No command here writes live state.
