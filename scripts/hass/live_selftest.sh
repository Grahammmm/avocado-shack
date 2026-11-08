#!/usr/bin/env bash
# HASS-LIVE-AUDIT-1: Hass live self-test for AgentOrange. Safe to run any time; an operator runs it by hand, or the
# candidate nightly timer (reports/hass/hass-selftest.{service,timer}.candidate, not installed) runs it.
#
#   scripts/hass/live_selftest.sh [--synthetic-only] [--model NAME] [--model-url URL] [--log FILE] [--brief FILE]
#                                 [--state-root DIR] [--growth-file FILE] [--min-free-mb MB]
#
# READ-ONLY on the live system: it restarts nothing, sends nothing, writes nothing in the Hass state or host dirs,
# opens no key or password file and reads no message text (every live tool it calls prints counts and check ids only).
# Synthetic data only:
#   synthetic   scripts/hass/live_selftest_synth.py: the real Mac forwarder classes -> a real host.py Server on
#               127.0.0.1 -> the host Worker -> relay -> forwarder pull/ack, in fresh temp dirs with a throwaway key:
#               forwarder->receiver path, status, reply-delivery recovery (no duplicate send), stranger ignored,
#               cancelled and expired codes do nothing
#   runtime     the runtime checkout (this script's checkout) is clean before and after
#   services    hass-receiver and hass-worker active; worker restart count
#   timers      hass-health.timer and hass-backup.timer active; their last run; newest backup age
#   health      hass/health.py read-only (no --seen, no --alert-log): db integrity, stuck inbox/outbox/relay,
#               mac-silent, writer, model reachable, disk
#   inbox       hass/inbox.py status: pending backlog (counts only)
#   model       only with --model: scripts/hass/live_selftest_model.py, 3 synthetic interpreter-eval cases through
#               the local model with the production timeout (a draft round trip; uses the CPU for a few minutes)
#   growth      state size, free disk and Hass journal lines in 24 h, compared with the previous run (--growth-file)
# Every command substitution that reads a command or helper (git, systemctl, health.py, inbox.py, the parser, find,
# date, du, df, journalctl, the synthetic and model helpers) keeps its own exit status, checked before the output is
# used. A check whose read fails reports `unknown` and FAILs: a failed acquisition is never shown as PASS, clean,
# healthy, "not run yet" or zero.
# Output: one `PASS|WARN|FAIL|SKIP <check> <detail>` line per check, then `HASS-SELFTEST <UTC> pass=.. warn=.. fail=..
# skip=..`; --log FILE appends that last line, --brief FILE replaces FILE with it (one line for the ops brief); a
# FAIL adds `failed:<check,...>`. Exit 0 no FAIL, 1 a FAIL, 2 bad usage.
# --synthetic-only runs only the synthetic check (what CI runs); it needs no live service.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
STATE_ROOT="$HOME/.local/state/hass"
GROWTH="$HOME/.local/state/hass-selftest/growth.tsv"
MODEL="" MODEL_URL="http://127.0.0.1:11434" LOG="" BRIEF="" SYNTH_ONLY=0 MIN_FREE_MB=1024
PY="${HASS_PYTHON:-/usr/bin/python3}"  # the interpreter the hass units use; tests pass their own
[ -x "$PY" ] || PY=python3

while [ $# -gt 0 ]; do
  case "$1" in
    --synthetic-only) SYNTH_ONLY=1 ;;
    --model) MODEL="${2:?}"; shift ;;
    --model-url) MODEL_URL="${2:?}"; shift ;;
    --log) LOG="${2:?}"; shift ;;
    --brief) BRIEF="${2:?}"; shift ;;
    --state-root) STATE_ROOT="${2:?}"; shift ;;
    --growth-file) GROWTH="${2:?}"; shift ;;
    --min-free-mb) MIN_FREE_MB="${2:?}"; shift ;;
    -h|--help) awk 'NR > 1 && /^set -u/ {exit} NR > 1' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

STATE="$STATE_ROOT/state" HOSTDIR="$STATE_ROOT/host" BACKUPS="$STATE_ROOT/backups"
NPASS=0 NWARN=0 NFAIL=0 NSKIP=0 FAILED=""
say() {  # say STATUS CHECK DETAIL...
  local s="$1" c="$2"; shift 2
  printf '%s %s %s\n' "$s" "$c" "$*"
  case "$s" in PASS) NPASS=$((NPASS + 1)) ;; WARN) NWARN=$((NWARN + 1)) ;; FAIL) NFAIL=$((NFAIL + 1)); FAILED="$FAILED $c" ;; *) NSKIP=$((NSKIP + 1)) ;; esac
}
PARSE="$REPO/scripts/hass/live_selftest_parse.py"  # validates health/inbox JSON; prints counts and check ids only
is_count() { case "${1:-x}" in ''|*[!0-9]*) return 1 ;; esac; }
tree_state() {  # prints clean, dirty, or `unknown (git exit N)`: a failed git call is never reported as clean
  local out rc
  out="$(git -C "$REPO" status --porcelain 2>/dev/null)"; rc=$?
  if [ $rc != 0 ]; then echo "unknown (git status exit $rc)"; elif [ -z "$out" ]; then echo clean; else echo dirty; fi
}

# -- runtime (before) ------------------------------------------------------------------------------------------
if [ "$SYNTH_ONLY" = 0 ]; then
  head="$(git -C "$REPO" rev-parse --short=12 HEAD 2>/dev/null)"; rc=$?
  tree="$(tree_state)"
  if [ $rc != 0 ] || [ -z "$head" ]; then say FAIL runtime "cannot read the checkout head (git rev-parse exit $rc)"
  elif [ "$tree" = clean ]; then say PASS runtime "checkout $head clean"
  elif [ "$tree" = dirty ]; then say FAIL runtime "checkout $head has local changes"
  else say FAIL runtime "checkout $head state $tree"; fi
fi

# -- synthetic end to end --------------------------------------------------------------------------------------
out="$("$PY" -B "$REPO/scripts/hass/live_selftest_synth.py" 2>&1)"; rc=$?
last="$(printf '%s\n' "$out" | tail -1)"
if [ $rc = 0 ]; then say PASS synthetic "$last"
else
  say FAIL synthetic "$last"
  printf '%s\n' "$out" | grep -E '^(FAIL|ERROR):' | sed 's/^/  /'
fi

if [ "$SYNTH_ONLY" = 0 ]; then
  # -- runtime (after: the synthetic run left nothing behind) --------------------------------------------------
  tree="$(tree_state)"
  if [ "$tree" = clean ]; then say PASS runtime-after "still clean"
  elif [ "$tree" = dirty ]; then say FAIL runtime-after "the checkout has local changes after the synthetic run"
  else say FAIL runtime-after "checkout state $tree"; fi

  # -- services --------------------------------------------------------------------------------------------------
  # Every systemctl read keeps its own exit status: PASS needs exit 0 and the expected output, never the output alone.
  for unit in hass-receiver hass-worker; do
    st="$(systemctl --user is-active "$unit.service" 2>/dev/null)"; arc=$?
    restarts="$(systemctl --user show -p NRestarts --value "$unit.service" 2>/dev/null)"; nrc=$?
    if [ $arc != 0 ] && [ "$st" = active ]; then say FAIL "service:$unit" "$unit.service state unknown (systemctl exit $arc)"
    elif [ "$st" != active ]; then say FAIL "service:$unit" "${st:-unknown} (systemctl exit $arc)"
    elif [ $nrc != 0 ]; then say FAIL "service:$unit" "active, restart counter unknown (systemctl exit $nrc)"
    elif ! is_count "$restarts"; then say FAIL "service:$unit" "active, restart counter unknown"
    elif [ "$restarts" -gt 0 ]; then say WARN "service:$unit" "active, systemd restart counter ${restarts} (crash restarts since the unit was loaded)"
    else say PASS "service:$unit" "active, 0 restarts"; fi
  done

  # -- timers ----------------------------------------------------------------------------------------------------
  for unit in hass-health hass-backup; do
    st="$(systemctl --user is-active "$unit.timer" 2>/dev/null)"; arc=$?
    lastrun="$(systemctl --user show -p LastTriggerUSec --value "$unit.timer" 2>/dev/null)"; lrc=$?
    status="$(systemctl --user show -p ExecMainStatus --value "$unit.service" 2>/dev/null)"; src=$?
    # All three reads must succeed before "has not run yet" is believed: a failed query is not proof of no run.
    if [ $arc != 0 ] && [ "$st" = active ]; then say FAIL "timer:$unit" "$unit.timer state unknown (systemctl exit $arc)"
    elif [ "$st" != active ]; then say FAIL "timer:$unit" "${st:-unknown} (systemctl exit $arc)"
    elif [ $lrc != 0 ]; then say FAIL "timer:$unit" "last trigger query failed (systemctl exit $lrc)"
    elif [ $src != 0 ]; then say FAIL "timer:$unit" "last run exit status unknown (systemctl exit $src)"
    elif [ -z "$lastrun" ] || [ "$lastrun" = n/a ] || [ "$lastrun" = 0 ]; then say WARN "timer:$unit" "active, has not run yet"
    elif ! is_count "$status"; then say FAIL "timer:$unit" "last run exit status unknown (not a number)"
    elif [ "$unit" = hass-health ] && [ "$status" -gt 1 ]; then say FAIL "timer:$unit" "last run exit $status"
    elif [ "$unit" = hass-backup ] && [ "$status" -ne 0 ]; then say FAIL "timer:$unit" "last run exit $status"
    else say PASS "timer:$unit" "active, last run $lastrun"; fi
  done
  if [ -d "$BACKUPS" ]; then
    found="$(find "$BACKUPS" -maxdepth 1 -name 'hass-state-*' -mmin -1560 2>/dev/null)"; brc=$?
  else found="" brc=0; fi  # no backups directory yet is "no backup", not a failed read
  if [ $brc != 0 ]; then say FAIL backup "cannot list the backups (find exit $brc)"
  elif [ -n "$found" ]; then say PASS backup "a backup under 26 h old exists"
  else say WARN backup "no backup under 26 h old"; fi

  # -- health (read-only: no --seen, no --alert-log) ---------------------------------------------------------------
  # Only a valid report counts: a crash (exit 1 with a traceback and no JSON) or a report whose ok disagrees with
  # its problems or its exit code is a FAIL, never the backup-age-only WARN.
  hout="$("$PY" -B "$REPO/hass/health.py" --state "$STATE" --backups "$BACKUPS" --writer --model "$MODEL_URL" \
          --host-dir "$HOSTDIR" --min-free-mb "$MIN_FREE_MB" 2>/dev/null)"; rc=$?
  ids="$(printf '%s\n' "$hout" | "$PY" -B "$PARSE" health 2>/dev/null)"; prc=$?
  if [ $rc != 0 ] && [ $rc != 1 ]; then say FAIL health "health.py exit $rc (unsafe state, crash or bad arguments)"
  elif [ $prc != 0 ]; then say FAIL health "health.py exit $rc without a valid report: ${ids:-parser exit $prc}"
  elif [ $rc = 0 ] && [ -z "$ids" ]; then say PASS health "no problems"
  elif [ $rc = 0 ]; then say FAIL health "health.py exit 0 but reported problems: $ids"
  elif [ -z "$ids" ]; then say FAIL health "health.py exit 1 but reported no problems"
  elif [ "$ids" = backup-age ]; then say WARN health "problems: $ids"
  else say FAIL health "problems: $ids"; fi

  # -- inbox ---------------------------------------------------------------------------------------------------
  iout="$("$PY" -B "$REPO/hass/inbox.py" status --state "$STATE" 2>/dev/null)"; rc=$?
  parsed="$(printf '%s\n' "$iout" | "$PY" -B "$PARSE" inbox 2>/dev/null)"; prc=$?
  read -r pending oldest done_n <<< "$parsed"
  if [ $rc != 0 ]; then say FAIL inbox "inbox.py status exit $rc"
  elif [ $prc != 0 ]; then say FAIL inbox "invalid report (parser exit $prc): ${parsed:-no output}"
  elif ! is_count "$pending" || ! is_count "$done_n" || { [ "$oldest" != null ] && ! is_count "$oldest"; }; then
    say FAIL inbox "parser output not counts"
  elif [ "$pending" = 0 ]; then say PASS inbox "pending 0, done $done_n"
  elif [ "$oldest" != null ] && [ "$oldest" -ge 15 ]; then say FAIL inbox "pending $pending, oldest ${oldest} min"
  else say WARN inbox "pending $pending, oldest ${oldest} min"; fi

  # -- model draft round trip (opt-in) -------------------------------------------------------------------------
  if [ -n "$MODEL" ]; then
    mout="$("$PY" -B "$REPO/scripts/hass/live_selftest_model.py" --url "$MODEL_URL" --model "$MODEL" 2>&1)"; rc=$?
    if [ $rc = 0 ]; then say PASS model "$(printf '%s' "$mout" | tail -1)"; else say FAIL model "$(printf '%s' "$mout" | tail -1)"; fi
  else
    say SKIP model "no --model given"
  fi

  # -- disk and log growth -------------------------------------------------------------------------------------
  # A failed measurement is reported as unknown and FAILs; it is never counted as 0 KB or 0 journal lines, and it
  # does not overwrite the previous run's baseline.
  now_s="$(date +%s)"; crc=$?
  [ $crc = 0 ] || now_s=""
  # Producer exit statuses are kept (a pipeline reports only its last stage): du can print a partial total and exit
  # 1 on an unreadable subtree, which is not a measurement.
  dout="$(du -sk "$STATE_ROOT" 2>/dev/null)"; drc=$?
  size_kb="$(printf '%s\n' "$dout" | cut -f1)"
  [ $drc = 0 ] || size_kb=""
  fout="$(df -Pm "$STATE_ROOT" 2>/dev/null)"; frc=$?
  free_mb="$(printf '%s\n' "$fout" | awk 'NR == 2 {print $4}')"
  [ $frc = 0 ] || free_mb=""
  jout="$(journalctl --user -q -u 'hass-*' --since -24h -o cat --no-pager 2>/dev/null)"; jrc=$?
  if [ $jrc != 0 ]; then lines=""; elif [ -z "$jout" ]; then lines=0; else lines="$(printf '%s\n' "$jout" | wc -l)"; fi
  unknown=""
  is_count "$now_s" || { now_s=""; unknown="$unknown clock (date exit $crc);"; }
  is_count "$size_kb" || { size_kb=""; unknown="$unknown state size (du exit $drc);"; }
  is_count "$free_mb" || { free_mb=""; unknown="$unknown free disk (df exit $frc);"; }
  is_count "$lines" || { lines=""; unknown="$unknown hass journal (journalctl exit $jrc);"; }
  detail="state ${size_kb:-unknown} KB, free ${free_mb:-unknown} MB, hass journal ${lines:-unknown} lines/24h"
  verdict=PASS
  if [ -n "$unknown" ]; then verdict=FAIL; detail="$detail; not measured:${unknown%;}"
  elif [ "$free_mb" -lt "$MIN_FREE_MB" ]; then verdict=FAIL
  elif [ "$lines" -gt 20000 ]; then verdict=WARN; fi
  if [ -r "$GROWTH" ] && [ -n "$size_kb" ]; then
    read -r p_s p_kb _p_free p_lines < "$GROWTH"
    if is_count "$p_s" && is_count "$p_kb"; then
      grow=$(( size_kb - p_kb ))
      detail="$detail; since last run $(( (now_s - p_s) / 3600 )) h ago: state ${grow} KB, journal was ${p_lines:-?} lines/24h"
      [ "$grow" -gt 51200 ] && [ "$verdict" = PASS ] && verdict=WARN
    fi
  fi
  say "$verdict" growth "$detail"
  if [ -z "$unknown" ] && mkdir -p "$(dirname "$GROWTH")" 2>/dev/null; then
    printf '%s %s %s %s\n' "$now_s" "$size_kb" "$free_mb" "$lines" > "$GROWTH" 2>/dev/null || true
  fi
fi

summary="HASS-SELFTEST $(date -u +%Y-%m-%dT%H:%M:%SZ) pass=$NPASS warn=$NWARN fail=$NFAIL skip=$NSKIP"
[ "$NFAIL" = 0 ] || summary="$summary failed:$(printf '%s' "$FAILED" | sed 's/^ //; s/ /,/g')"
echo "$summary"
if [ -n "$LOG" ]; then printf '%s\n' "$summary" >> "$LOG"; fi
if [ -n "$BRIEF" ]; then printf '%s\n' "$summary" > "$BRIEF.tmp.$$" && mv -f "$BRIEF.tmp.$$" "$BRIEF"; fi
[ "$NFAIL" = 0 ]
