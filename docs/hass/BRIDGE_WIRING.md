# Hass bridge wiring: BlueBubbles, the Mac forwarder and AgentOrange (HASS-MAC-KIT-1)

Names and shapes only. No value, password, key, address, phone or IP is ever written here, in Git, a card or a log.
Source of truth for the exact key sets: `mac/hass_forwarder.py` and `hass/host.py` (HASS-FWD-1, HASS-RCV-1); order of work: [MAC_RUNBOOK.md](MAC_RUNBOOK.md).

## Direction of traffic (why no BlueBubbles URL goes over Tailscale)

```
phone --iMessage--> dedicated Apple ID (Messages on the Mac)
                       |
                BlueBubbles Server  (127.0.0.1:<bbPort>, loopback only)
                  |  webhook doorbell -> forwarder 127.0.0.1:8796
                  v
           Mac forwarder (launchd, dedicated user)
                  |  sealed envelope, Mac initiates, over Tailscale
                  v
        AgentOrange receiver  http://<agentorange tailnet name>:8795   (/v1/inbound, /v1/relay)
```

AgentOrange never calls BlueBubbles. The Mac forwarder talks to BlueBubbles on loopback and pushes sealed envelopes to
AgentOrange; replies (and up to two result pictures) come back through the sealed relay and the forwarder sends them to the
owner chat through loopback BlueBubbles. So the "BlueBubbles URL over Tailscale" is, by design, **not** published: the URL
is `http://127.0.0.1:<bbPort>` on the Mac only, and the runbook (step 8) requires the macOS firewall and no proxy,
tunnel or dynamic DNS. Exposing it on the tailnet would be a design change needing G's decision. (Reading: this follows the merged code; UNVERIFIED on a real Mac.)

## Mac side: `~/Library/Application Support/HassForwarder/config.json` (0600)

Closed key set (any other key is refused):

| key | holds | notes |
|---|---|---|
| `ownerChat` | `iMessage;-;<owner address>` | one-to-one owner chat only |
| `receiverUrl` | `http://<agentorange tailnet name>:8795` | host must be loopback or in 100.64.0.0/10; port 8795; no path/credentials |
| `bbPort` | integer | BlueBubbles port shown in its settings (default 1234) |
| `bbPasswordFile` | absolute path | file name `bb-password`: the BlueBubbles **server password**, 0600. Password name only; value never leaves the Mac |
| `secretFile` | absolute path | `envelope.key`: 64 hex, 0600, copied once to AgentOrange |
| `spoolDir` | absolute path | `spool`, 0700, must exist |
| `webhookPort` | integer, optional | 8796, loopback |
| `webhookTokenFile` | absolute path | `webhook.token`: 64 hex, 0600; the BlueBubbles webhook is `http://127.0.0.1:8796/bb/<token>` for new-message and updated-message only |

BlueBubbles settings that the kit assumes: server password set; Private API **off**; SIP untouched; no proxy/tunnel/dynamic DNS; webhooks as above.

## AgentOrange side: `~/.local/state/hass/host/host.json` (0600)

Keys the bridge needs for this link: `listen` (`<agentorange tailnet IP>:8795`), `allowedPeers` (`[<Mac tailnet IP>]`),
`secretFile` (`~/.config/hass/envelope.key`, same bytes as the Mac `envelope.key`), `approvals` (`hold` until the first
private yes, then `private`, later `live`), `pictures` (true; required for live), `runtimeCommit`, plus `state`, `interpreter` and `previewer` per the runbook. State `config.json` settings: `ownerSenders`, `ownerChat`.

## How AgentOrange reaches the Mac

1. **Data path:** it does not; the Mac initiates. AgentOrange only listens on 8795, restricted by `allowedPeers` and the Tailscale access-control rule (only this Mac may reach `agentorange:8795`).
2. **Files:** code bundle and `envelope.key` move by Taildrop (`tailscale file cp`), UNVERIFIED on this tailnet; USB fallback in the runbook.
3. **Optional shell access:** only if G chose step 10 of [MAC_MINI_FINAL_STEPS.md](MAC_MINI_FINAL_STEPS.md) (Remote Login for the `hass` user with AgentOrange's **public** key). Not needed and not used by the bridge.
4. **Health:** AgentOrange `hass-health.timer` reports `mac-silent` when the forwarder stops posting (HASS-SVC-1); on the Mac `hass_forwarder.py check` expects `{"reachable":2}`.

## Checker and installer

`scripts/hass/mac_setup_check.sh` (read-only, prints PASS/FAIL/WARN, never prints addresses or secrets) and
`scripts/hass/mac_install.sh` (pinned BlueBubbles Server v1.9.12, sha256 and size verified, no sudo). Pin recorded 2026-11-07 from the GitHub release page (published 2026-10-27) and confirmed by hashing both downloads; re-pin by editing the constants in `mac_install.sh` and `hass/tests/test_mac_kit.py` together.
