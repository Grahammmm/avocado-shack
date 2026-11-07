#!/usr/bin/env bash
# AV-CI-FLAKE-1: install the pinned Playwright and its Chromium once per host and version, into a folder
# no other job writes, and never rewrite it while jobs use it.
#
# Why: the AgentOrange runners agentorange-avo-1..8 share one $HOME. The old step restored an actions/cache
# tarball (~300 MB) over ~/pw-tools and ~/.cache/ms-playwright at the start of EVERY job. tar replaces
# each file, so for a few seconds the chrome-headless-shell binary and the playwright package files are
# being written while browser tests in the other jobs launch Chromium from the same paths:
# `browserType.launch: spawn ETXTBSY` (exec of a file open for writing), or a half-written package file.
# Measured 2026-11-06: PR #481 shard 2 and PR #484 shard 0 both failed at 23:58:55-56Z, inside the
# 23:58:50-23:58:56Z tar -xf of PR #481 shard 3's cache restore.
#
# Now: package and browsers live in <root>/<version>. It is built only while holding a host-wide lock and
# only when its .ready marker is missing; .ready is written last, and no job uses the folder before it
# exists, so a job never sees a half-built install and a ready folder is never written again.
# Branches still on the old step keep rewriting ~/pw-tools and ~/.cache/ms-playwright, so this job's browser
# comes from its own folder: PLAYWRIGHT_BROWSERS_PATH for every Playwright launch, and CHROMIUM_PATH for
# scripts that pass only that through (hass/preview.py).
#
# env: PLAYWRIGHT_VERSION (required); AVO_PW_ROOT (default ~/.cache/avo-ci-playwright).
# Writes PLAYWRIGHT_MODULE, PLAYWRIGHT_BROWSERS_PATH and CHROMIUM_PATH to $GITHUB_ENV when it is set.
set -euo pipefail
version="${PLAYWRIGHT_VERSION:?PLAYWRIGHT_VERSION is not set}"
case "$version" in *[!0-9A-Za-z.-]* | '') echo "bad PLAYWRIGHT_VERSION: $version" >&2; exit 2 ;; esac
root="${AVO_PW_ROOT:-$HOME/.cache/avo-ci-playwright}"
prefix="$root/$version"
module="$prefix/node_modules/playwright"
browsers="$prefix/browsers"
mkdir -p "$root"
exec 9>"$root/.lock"
if ! flock -w 900 9; then echo "timed out waiting for another job's Playwright install" >&2; exit 1; fi
if [ -f "$prefix/.ready" ]; then
  echo "Playwright $version already installed at $prefix (not rewritten)"
else
  rm -rf "$prefix"  # a leftover from a killed install: never ready, so never used (we hold the lock)
  mkdir -p "$prefix"
  npm install --prefix "$prefix" --no-save --no-audit --no-fund "playwright@$version"
  PLAYWRIGHT_BROWSERS_PATH="$browsers" "$prefix/node_modules/.bin/playwright" install chromium
  touch "$prefix/.ready"
  echo "Playwright $version installed at $prefix"
fi
flock -u 9
# The headless shell is what chromium.launch({headless: true}) runs when no executablePath is given.
shells=("$browsers"/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell)
if [ "${#shells[@]}" -ne 1 ] || [ ! -x "${shells[0]}" ]; then
  echo "expected one chrome-headless-shell under $browsers, found: ${shells[*]}" >&2
  exit 1
fi
chromium="${shells[0]}"
echo "PLAYWRIGHT_MODULE=$module"
echo "CHROMIUM_PATH=$chromium"
if [ -n "${GITHUB_ENV:-}" ]; then
  {
    echo "PLAYWRIGHT_MODULE=$module"
    echo "PLAYWRIGHT_BROWSERS_PATH=$browsers"
    echo "CHROMIUM_PATH=$chromium"
  } >> "$GITHUB_ENV"
fi
