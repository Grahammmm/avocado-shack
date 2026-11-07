#!/bin/bash
# Hass Mac mini installer for BlueBubbles Server (HASS-MAC-KIT-1). Idempotent. No sudo anywhere.
# Run as the dedicated Hass user. Touches only: ~/Applications/BlueBubbles.app, two LaunchAgents labelled
# com.avocadoshack.hass-bluebubbles and com.avocadoshack.hass-keepawake, and ~/Library/Application Support/HassForwarder/kit.
# It never reads Messages data, never changes macOS security (SIP stays on; Private API stays off) and sends nothing.
#
# Usage:  bash mac_install.sh [--print-plan | --dry-run]
#   --print-plan  print the pinned release facts and exit (no network, no changes)
#   --dry-run     also compare against the live GitHub release page, but download and change nothing
# UNVERIFIED on a real Mac: the unzip, launchctl and first-launch behaviour below were written from documentation.

set -u

# ---- Pinned release (official: github.com/BlueBubblesApp/bluebubbles-server/releases) ----
# Recorded 2026-11-07 from the release page API (published_at 2026-10-27T23:04:07Z, tag v1.9.12, not a prerelease),
# and re-checked by downloading both files and hashing them with sha256sum: the hashes below matched.
PIN_TAG="v1.9.12"
PIN_VERSION="1.9.12"
PIN_PUBLISHED="2026-10-27T23:04:07Z"
PIN_RECORDED="2026-11-07"
PIN_REPO="BlueBubblesApp/bluebubbles-server"
ARM_NAME="BlueBubbles-1.9.12-arm64-mac.zip"
ARM_SIZE="296262790"
ARM_SHA256="e1d96d67fe4fc79ad44a8f1eeac3de78eef561635842b66d380dd3eba5092d89"
X64_NAME="BlueBubbles-1.9.12-mac.zip"
X64_SIZE="302631985"
X64_SHA256="7078ea4302b4df6ab4b236bdaea84440aabf95b2a07b281919fd0ef8822e958c"

MODE="install"
case "${1:-}" in
  "") ;;
  --print-plan) MODE="plan" ;;
  --dry-run) MODE="dry" ;;
  *) echo "usage: bash mac_install.sh [--print-plan | --dry-run]"; exit 2 ;;
esac

die() { echo "REFUSED: $1" >&2; exit 1; }

# Architecture picks the asset. MAC_INSTALL_ARCH is only for the offline test.
arch="${MAC_INSTALL_ARCH:-$(uname -m)}"
case "$arch" in
  arm64) NAME="$ARM_NAME"; SIZE="$ARM_SIZE"; SHA="$ARM_SHA256" ;;
  x86_64) NAME="$X64_NAME"; SIZE="$X64_SIZE"; SHA="$X64_SHA256" ;;
  *) die "unknown CPU architecture '$arch'" ;;
esac
URL="https://github.com/${PIN_REPO}/releases/download/${PIN_TAG}/${NAME}"

echo "BlueBubbles Server $PIN_VERSION ($PIN_TAG), published $PIN_PUBLISHED, pinned $PIN_RECORDED"
echo "  file:   $NAME"
echo "  size:   $SIZE bytes"
echo "  sha256: $SHA"
echo "  from:   $URL"
[ "$MODE" = "plan" ] && exit 0

command -v curl >/dev/null 2>&1 || die "curl not found"
command -v shasum >/dev/null 2>&1 || die "shasum not found"

APP_DIR="$HOME/Applications"
APP="$APP_DIR/BlueBubbles.app"
KIT="$HOME/Library/Application Support/HassForwarder/kit"
AGENTS="$HOME/Library/LaunchAgents"
LABEL_APP="com.avocadoshack.hass-bluebubbles"
LABEL_AWAKE="com.avocadoshack.hass-keepawake"
UIDN="$(id -u)"

# ---- Compare with the live release page before downloading; any difference is a refusal ----
meta="$(curl -fsS -m 30 "https://api.github.com/repos/${PIN_REPO}/releases/tags/${PIN_TAG}" 2>/dev/null)"
if [ -n "$meta" ]; then
  live="$(printf '%s\n' "$meta" | awk -v n="\"name\": \"$NAME\"" '
    index($0, n) {f=1; next}
    f && /"size":/ {gsub(/[^0-9]/, "", $0); size=$0}
    f && /"digest":/ {d=$0; sub(/.*sha256:/, "", d); sub(/".*/, "", d); print size " " d; exit}')"
  live_size="${live%% *}"
  live_sha="${live##* }"
  [ -n "$live" ] || die "$NAME not found on the live $PIN_TAG release page"
  [ "$live_size" = "$SIZE" ] || die "live release size $live_size differs from pinned $SIZE"
  [ "$live_sha" = "$SHA" ] || die "live release sha256 differs from the pinned value"
  echo "Release page matches the pin."
else
  echo "NOTE: could not read the release page; relying on the sha256 check after download."
fi
[ "$MODE" = "dry" ] && { echo "Dry run: nothing downloaded or changed."; exit 0; }

# ---- Already installed at the pinned version? Skip the download. ----
installed=""
if [ -d "$APP" ]; then
  installed="$(defaults read "$APP/Contents/Info" CFBundleShortVersionString 2>/dev/null)"
fi
if [ "$installed" = "$PIN_VERSION" ]; then
  echo "BlueBubbles $PIN_VERSION is already installed: skipping download."
else
  pgrep -x BlueBubbles >/dev/null 2>&1 && die "BlueBubbles is running; Quit it (menu bar icon > Quit), then run this again"
  umask 077
  mkdir -p "$KIT" "$APP_DIR" || die "cannot create $KIT"
  zip="$KIT/$NAME"
  echo "Downloading (about $((SIZE / 1048576)) MB)..."
  curl -fL --proto '=https' --tlsv1.2 -o "$zip.part" "$URL" || { rm -f "$zip.part"; die "download failed"; }
  got_size="$(stat -f %z "$zip.part" 2>/dev/null || wc -c < "$zip.part")"
  got_sha="$(shasum -a 256 "$zip.part" | awk '{print $1}')"
  if [ "$got_size" != "$SIZE" ] || [ "$got_sha" != "$SHA" ]; then
    rm -f "$zip.part"
    die "downloaded file does not match the pin (size $got_size, sha256 $got_sha); deleted it"
  fi
  mv "$zip.part" "$zip"
  echo "Download verified (size and sha256 match)."
  stage="$KIT/unpack-$$"
  mkdir -p "$stage" || die "cannot create staging folder"
  ditto -x -k "$zip" "$stage" || { die "unzip failed"; }
  [ -d "$stage/BlueBubbles.app" ] || die "BlueBubbles.app not found in the zip"
  if [ -d "$APP" ]; then mv "$APP" "$KIT/BlueBubbles.app.previous-$$" || die "cannot move the old app aside"; fi
  mv "$stage/BlueBubbles.app" "$APP" || die "cannot place the app"
  rmdir "$stage" 2>/dev/null
  rm -f "$zip"
  echo "Installed $APP"
fi

# ---- Launch-at-login item (a LaunchAgent: no prompt, no sudo, removable by deleting the one file) ----
mkdir -p "$AGENTS" "$KIT" || die "cannot create $AGENTS"
write_agent() { # label, then program arguments as <string> lines on stdin
  local label="$1" plist="$AGENTS/$1.plist" tmp="$AGENTS/$1.plist.new"
  { printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
      '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
      '<plist version="1.0"><dict>' "  <key>Label</key><string>$label</string>" '  <key>ProgramArguments</key><array>'
    cat
    printf '%s\n' '  </array>' '  <key>RunAtLoad</key><true/>' "$2" '</dict></plist>'
  } > "$tmp"
  if [ -f "$plist" ] && cmp -s "$tmp" "$plist"; then rm -f "$tmp"; return 1; fi
  mv "$tmp" "$plist"
  return 0 # 0 = written, 1 = already identical (ignored by callers)
}
write_agent "$LABEL_APP" '  <key>ProcessType</key><string>Interactive</string>' <<EOF
    <string>/usr/bin/open</string><string>-a</string><string>$APP</string>
EOF
write_agent "$LABEL_AWAKE" '  <key>KeepAlive</key><true/>' <<EOF
    <string>/usr/bin/caffeinate</string><string>-i</string><string>-s</string>
EOF
for label in "$LABEL_APP" "$LABEL_AWAKE"; do
  if ! launchctl print "gui/$UIDN/$label" >/dev/null 2>&1; then
    launchctl bootstrap "gui/$UIDN" "$AGENTS/$label.plist" 2>/dev/null && echo "Loaded login item $label" || echo "NOTE: could not load $label now; it will load at next login"
  else
    echo "Login item $label already loaded."
  fi
done

cat <<'EOF'

Done with the automatic part. What is left, in order (details in docs/hass/MAC_MINI_FINAL_STEPS.md):
  1. Open BlueBubbles (it may already be open), and approve the macOS permission prompts it shows.
  2. In BlueBubbles, set a server password (privately) and leave Private API OFF.
  3. Run scripts/hass/mac_setup_check.sh and confirm it prints no FAIL.
Remove everything this script added: delete ~/Applications/BlueBubbles.app and the two plists named above in
~/Library/LaunchAgents (after: launchctl bootout gui/$(id -u)/<label>).
EOF
