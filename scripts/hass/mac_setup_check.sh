#!/bin/bash
# Hass Mac mini setup checker (HASS-MAC-KIT-1). READ-ONLY: changes nothing, sends nothing, needs no sudo.
# G pastes this into Terminal on the Mac mini, as the dedicated Hass user. Prints PASS / FAIL / WARN per item.
# Prints no addresses, IPs, passwords or message text. Exit status 1 if any FAIL.
# Optional env: BB_PORT (default 1234), RECEIVER_HOST (AgentOrange tailnet name; checks port 8795 is reachable).
# UNVERIFIED on a real Mac: every check below is written from documentation and has never run on the target.

BB_PORT="${BB_PORT:-1234}"
RECEIVER_HOST="${RECEIVER_HOST:-}"
KIT_LABEL_AWAKE="com.avocadoshack.hass-keepawake"
fails=0
warns=0

pass() { printf 'PASS  %s\n' "$1"; }
fail() { printf 'FAIL  %s\n' "$1"; fails=$((fails + 1)); }
warn() { printf 'WARN  %s\n' "$1"; warns=$((warns + 1)); }

printf 'Hass Mac setup check (read-only). BlueBubbles port %s.\n' "$BB_PORT"

# 1. macOS version (BlueBubbles Server minimum is UNVERIFIED; 12 or newer is required here).
if command -v sw_vers >/dev/null 2>&1; then
  ver="$(sw_vers -productVersion 2>/dev/null)"
  major="${ver%%.*}"
  case "$major" in
    ''|*[!0-9]*) fail "macOS version unreadable" ;;
    *) if [ "$major" -ge 12 ]; then pass "macOS $ver (12 or newer)"; else fail "macOS $ver is older than 12"; fi ;;
  esac
else
  fail "not macOS (sw_vers missing)"
fi

# 2. Messages / Apple Account signed in. Heuristic only (UNVERIFIED): the iCloud account list for this user.
#    This is a necessary, not sufficient, sign. The real proof is the self-test message in the final steps.
if defaults read MobileMeAccounts Accounts >/dev/null 2>&1; then
  n="$(defaults read MobileMeAccounts Accounts 2>/dev/null | grep -c 'AccountID')"
  if [ "${n:-0}" -ge 1 ]; then
    pass "an Apple Account is signed in for this user ($n); confirm Messages > Settings > iMessage shows it"
  else
    fail "no Apple Account signed in for this user"
  fi
else
  fail "no Apple Account signed in for this user"
fi

# 3. BlueBubbles installed and running.
bb_app=""
for p in "$HOME/Applications/BlueBubbles.app" "/Applications/BlueBubbles.app"; do
  if [ -d "$p" ]; then bb_app="$p"; break; fi
done
if [ -n "$bb_app" ]; then
  bbv="$(defaults read "$bb_app/Contents/Info" CFBundleShortVersionString 2>/dev/null)"
  pass "BlueBubbles installed (version ${bbv:-unknown})"
else
  fail "BlueBubbles.app not found in ~/Applications or /Applications"
fi
if pgrep -x BlueBubbles >/dev/null 2>&1; then
  pass "BlueBubbles is running"
else
  fail "BlueBubbles is not running"
fi

# 4. Port. Hass keeps BlueBubbles on loopback: the Mac forwarder talks to it locally and reaches AgentOrange
#    over Tailscale. So: loopback must answer; a Tailscale-address listener is a WARN (not wanted).
code="$(curl -s -m 5 -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BB_PORT}/api/v1/ping" 2>/dev/null)"
case "$code" in
  200|401|403) pass "BlueBubbles answers on loopback port $BB_PORT (HTTP $code; 401/403 just means the password is required)" ;;
  *) fail "nothing answers on loopback port $BB_PORT (got '${code:-none}'); set BB_PORT if the app uses another port" ;;
esac
if command -v lsof >/dev/null 2>&1; then
  wide="$(lsof -nP -iTCP:"$BB_PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR>1 && $9 !~ /^(127\.0\.0\.1|\[::1\]|localhost):/ {print "x"}' | head -1)"
  if [ -n "$wide" ]; then
    warn "port $BB_PORT listens beyond loopback; the runbook wants loopback only (turn on the macOS firewall, step 8)"
  else
    pass "port $BB_PORT is loopback only (as the runbook wants)"
  fi
fi
ts=""
for p in /Applications/Tailscale.app/Contents/MacOS/Tailscale "$(command -v tailscale 2>/dev/null)"; do
  if [ -n "$p" ] && [ -x "$p" ]; then ts="$p"; break; fi
done
if [ -n "$ts" ]; then
  if "$ts" status >/dev/null 2>&1; then pass "Tailscale is up"; else fail "Tailscale is installed but not connected"; fi
else
  fail "Tailscale not found"
fi
if [ -n "$RECEIVER_HOST" ]; then
  if nc -z -G 5 "$RECEIVER_HOST" 8795 >/dev/null 2>&1; then
    pass "AgentOrange receiver port 8795 is reachable over Tailscale"
  else
    warn "AgentOrange receiver port 8795 not reachable (expected until the receiver service is started, runbook step 17)"
  fi
else
  warn "RECEIVER_HOST not set: skipped the AgentOrange port 8795 check (run: RECEIVER_HOST=<agentorange tailnet name> bash mac_setup_check.sh)"
fi

# 5. Awake: system sleep disabled, either by the power setting or by the kit's keep-awake agent.
sleepval="$(pmset -g 2>/dev/null | awk '$1=="sleep" {print $2; exit}')"
if [ "$sleepval" = "0" ]; then
  pass "system sleep is off (pmset sleep 0)"
elif launchctl list 2>/dev/null | grep -q "$KIT_LABEL_AWAKE" && pgrep -x caffeinate >/dev/null 2>&1; then
  pass "kit keep-awake agent is running (caffeinate)"
else
  fail "Mac may sleep (pmset sleep=${sleepval:-unknown}, no kit keep-awake agent); run mac_install.sh or set sleep to never"
fi

# 6. Disk space on the home volume: at least 10 GB free.
free_kb="$(df -k "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')"
case "$free_kb" in
  ''|*[!0-9]*) fail "free disk space unreadable" ;;
  *) if [ "$free_kb" -ge 10485760 ]; then pass "free disk space $((free_kb / 1048576)) GB (10 GB needed)"; else fail "only $((free_kb / 1048576)) GB free (10 GB needed)"; fi ;;
esac

printf '\n%s FAIL, %s WARN. ' "$fails" "$warns"
if [ "$fails" -eq 0 ]; then printf 'Ready for the next step.\n'; exit 0; fi
printf 'Fix the FAIL lines, then run this again.\n'
exit 1
