#!/usr/bin/env bash
# HASS-LIVE-AUDIT-1: Hass live self-test for AgentOrange. Safe to run any time; an operator runs it by hand, or the
# candidate nightly timer (deploy/hass/hass-selftest.*.candidate) runs it.
#
#   scripts/hass/live_selftest.sh [--synthetic-only] [--model NAME] [--model-url URL] [--log FILE]
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
# Output: one `PASS|WARN|FAIL|SKIP <check> <detail>` line per check, then `HASS-SELFTEST <UTC> pass=.. warn=.. fail=..
# skip=..`; --log FILE appends that last line. Exit 0 no FAIL, 1 a FAIL, 2 bad usage.
# --synthetic-only runs only the synthetic check (what CI runs); it needs no live service.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
STATE_ROOT="$HOME/.local/state/hass"
GROWTH="$HOME/.local/state/hass-selftest/growth.tsv"
MODEL="" MODEL_URL="http://127.0.0.1:11434" LOG="" SYNTH_ONLY=0 MIN_FREE_MB=1024
PY=/usr/bin/python3
[ -x "$PY" ] || PY=python3

while [ $# -gt 0 ]; do
  case "$1" in
    --synthetic-only) SYNTH_ONLY=1 ;;
    --model) MODEL="${2:?}"; shift ;;
    --model-url) MODEL_URL="${2:?}"; shift ;;
    --log) LOG="${2:?}"; shift ;;
    --state-root) STATE_ROOT="${2:?}"; shift ;;
    --growth-file) GROWTH="${2:?}"; shift ;;
    --min-free-mb) MIN_FREE_MB="${2:?}"; shift ;;
    -h|--help) sed -n '2,27p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

STATE="$STATE_ROOT/state" HOSTDIR="$STATE_ROOT/host" BACKUPS="$STATE_ROOT/backups"
NPASS=0 NWARN=0 NFAIL=0 NSKIP=0
say() {  # say STATUS CHECK DETAIL...
  local s="$1" c="$2"; shift 2
  printf '%s %s %s\n' "$s" "$c" "$*"
  case "$s" in PASS) NPASS=$((NPASS + 1)) ;; WARN) NWARN=$((NWARN + 1)) ;; FAIL) NFAIL=$((NFAIL + 1)) ;; *) NSKIP=$((NSKIP + 1)) ;; esac
}
field() {  # field NAME JSON -> the bare value of a top-level number/null field (counts only)
  printf '%s' "$2" | grep -o "\"$1\": [0-9a-z.]*" | head -1 | sed 's/.*: //'
}
clean_tree() { [ -z "$(git -C "$REPO" status --porcelain 2>/dev/null)" ]; }

# -- runtime (before) ------------------------------------------------------------------------------------------
if [ "$SYNTH_ONLY" = 0 ]; then
  head="$(git -C "$REPO" rev-parse --short=12 HEAD 2>/dev/null || echo none)"
  if clean_tree; then say PASS runtime "checkout $head clean"; else say FAIL runtime "checkout $head has local changes"; fi
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
  if clean_tree; then say PASS runtime-after "still clean"; else say FAIL runtime-after "the synthetic run changed the checkout"; fi

  # -- services --------------------------------------------------------------------------------------------------
  for unit in hass-receiver hass-worker; do
    st="$(systemctl --user is-active "$unit.service" 2>/dev/null)"
    restarts="$(systemctl --user show -p NRestarts --value "$unit.service" 2>/dev/null)"
    if [ "$st" != active ]; then say FAIL "service:$unit" "$st"
    elif [ "${restarts:-0}" -gt 0 ]; then say WARN "service:$unit" "active, restarted ${restarts} times since it was started"
    else say PASS "service:$unit" "active, 0 restarts"; fi
  done

  # -- timers ----------------------------------------------------------------------------------------------------
  for unit in hass-health hass-backup; do
    st="$(systemctl --user is-active "$unit.timer" 2>/dev/null)"
    lastrun="$(systemctl --user show -p LastTriggerUSec --value "$unit.timer" 2>/dev/null)"
    status="$(systemctl --user show -p ExecMainStatus --value "$unit.service" 2>/dev/null)"
    if [ "$st" != active ]; then say FAIL "timer:$unit" "$st"
    elif [ -z "$lastrun" ] || [ "$lastrun" = n/a ] || [ "$lastrun" = 0 ]; then say WARN "timer:$unit" "active, has not run yet"
    elif [ "$unit" = hass-health ] && [ "${status:-0}" -gt 1 ]; then say FAIL "timer:$unit" "last run exit $status"
    elif [ "$unit" = hass-backup ] && [ "${status:-0}" -ne 0 ]; then say FAIL "timer:$unit" "last run exit $status"
    else say PASS "timer:$unit" "active, last run $lastrun"; fi
  done
  newest="$(find "$BACKUPS" -maxdepth 1 -name 'hass-state-*' -mmin -1560 2>/dev/null | head -1)"
  if [ -n "$newest" ]; then say PASS backup "a backup under 26 h old exists"
  else say WARN backup "no backup under 26 h old"; fi

  # -- health (read-only: no --seen, no --alert-log) ---------------------------------------------------------------
  hout="$("$PY" -B "$REPO/hass/health.py" --state "$STATE" --backups "$BACKUPS" --writer --model "$MODEL_URL" \
          --host-dir "$HOSTDIR" --min-free-mb "$MIN_FREE_MB" 2>&1)"; rc=$?
  ids="$(printf '%s' "$hout" | grep -o '"check": "[a-z-]*"' | sed 's/"check": "//; s/"//' | sort -u | tr '\n' ' ')"
  if [ $rc = 0 ]; then say PASS health "no problems"
  elif [ $rc = 1 ] && [ "$(printf '%s' "$ids" | tr ' ' '\n' | grep -cv -e '^backup-age$' -e '^$')" = 0 ]; then say WARN health "problems: $ids"
  elif [ $rc = 1 ]; then say FAIL health "problems: $ids"
  else say FAIL health "health.py exit $rc (unsafe state or bad arguments)"; fi

  # -- inbox ---------------------------------------------------------------------------------------------------
  iout="$("$PY" -B "$REPO/hass/inbox.py" status --state "$STATE" 2>&1)"; rc=$?
  pending="$(field pending "$iout")" oldest="$(field oldest_pending_minutes "$iout")" done_n="$(field done "$iout")"
  if [ $rc != 0 ]; then say FAIL inbox "inbox.py status exit $rc"
  elif [ "${pending:-x}" = 0 ]; then say PASS inbox "pending 0, done ${done_n:-?}"
  elif [ "${oldest:-0}" != null ] && [ "${oldest%.*}" -ge 15 ] 2>/dev/null; then say FAIL inbox "pending $pending, oldest ${oldest} min"
  else say WARN inbox "pending $pending, oldest ${oldest} min"; fi

  # -- model draft round trip (opt-in) -------------------------------------------------------------------------
  if [ -n "$MODEL" ]; then
    mout="$("$PY" -B "$REPO/scripts/hass/live_selftest_model.py" --url "$MODEL_URL" --model "$MODEL" 2>&1)"; rc=$?
    if [ $rc = 0 ]; then say PASS model "$(printf '%s' "$mout" | tail -1)"; else say FAIL model "$(printf '%s' "$mout" | tail -1)"; fi
  else
    say SKIP model "no --model given"
  fi

  # -- disk and log growth -------------------------------------------------------------------------------------
  now_s="$(date +%s)"
  size_kb="$(du -sk "$STATE_ROOT" 2>/dev/null | cut -f1)"
  free_mb="$(df -Pm "$STATE_ROOT" 2>/dev/null | awk 'NR == 2 {print $4}')"
  lines="$(journalctl --user -u 'hass-*' --since -24h -o cat --no-pager 2>/dev/null | wc -l)"
  detail="state ${size_kb:-?} KB, free ${free_mb:-?} MB, hass journal ${lines} lines/24h"
  verdict=PASS
  [ "${free_mb:-0}" -lt "$MIN_FREE_MB" ] && verdict=FAIL
  [ "${lines:-0}" -gt 20000 ] && [ "$verdict" = PASS ] && verdict=WARN
  if [ -r "$GROWTH" ]; then
    read -r p_s p_kb _p_free p_lines < "$GROWTH"
    grow=$(( ${size_kb:-0} - ${p_kb:-0} ))
    detail="$detail; since last run $(( (now_s - ${p_s:-now_s}) / 3600 )) h ago: state ${grow} KB, journal was ${p_lines:-?} lines/24h"
    [ "$grow" -gt 51200 ] && [ "$verdict" = PASS ] && verdict=WARN
  fi
  say "$verdict" growth "$detail"
  if mkdir -p "$(dirname "$GROWTH")" 2>/dev/null; then
    printf '%s %s %s %s\n' "$now_s" "${size_kb:-0}" "${free_mb:-0}" "${lines:-0}" > "$GROWTH" 2>/dev/null || true
  fi
fi

summary="HASS-SELFTEST $(date -u +%Y-%m-%dT%H:%M:%SZ) pass=$NPASS warn=$NWARN fail=$NFAIL skip=$NSKIP"
echo "$summary"
if [ -n "$LOG" ]; then printf '%s\n' "$summary" >> "$LOG"; fi
[ "$NFAIL" = 0 ]
