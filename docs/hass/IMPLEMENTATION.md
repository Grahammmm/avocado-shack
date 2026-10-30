# Hass implementation plan

**Proposed architecture; no bridge, owner editing service or Hass runtime is installed by this plan.** Keep the existing website private throughout development. Start with a narrow editing workflow, not a general agent with unrestricted access to the machine.

## Current baseline

Verified October 30, 2026 before this documentation change: Agent Orange and GitHub `main` both at `0d29ba0e5d108b3513e1a9b92ca37bc592371c3b`, working tree clean; GitHub visibility private; `avocado-shack-sandbox.service` active. These are source/service checks, not a fresh browser or message-integration test.

| Component | Current state | Planned change |
| --- | --- | --- |
| `storefront-mockup/catalog-products.js` | 170 static records | Canonical validated catalog records; keep stable IDs and render output compatible |
| `producers.json` + `producers.js` | Two matching representations | One editable source with generated browser output |
| `community.json` | Real events empty; undated route ideas | Validated event commands with confirmed owner details |
| `hiking-preview.json` | Separate labeled mock invitations/history | Keep separate; never promote samples into actual events by inference |
| `index.html` and `/hike` | Existing private site | Structured copy/hours/image fields for routine edits; preserve design |
| `community-server.py` | Local public-facing subscription/RSVP routes | Preserve these routes; add a separate private owner-command service, not anonymous write routes |
| Community SQLite | Private subscribers/RSVPs | Read aggregate guest counts when needed; no import into Git or the content store |
| Hass state and media inbox | Not implemented | Separate private queue, approvals, media originals and audit records |

Suggested source location for new code: `hass/`, with `adapters/`, `content/`, `tools/` and `tests/`. This is a proposed structure, not an existing directory. Reuse the existing Python runtime for deterministic validation and file operations where practical. Keep messaging and model adapters replaceable. Inspect available dependencies before choosing additional packages; do not introduce a large commerce framework or CMS just for these edits.

## Message and approval flow

1. A dedicated Mac receives a new message in the allowed owner's one-to-one iMessage conversation.
2. The local bridge adapter checks sender/chat, ignores outbound echoes and updates, and stores the provider message ID before acknowledging receipt.
3. It sends only the relevant message/media to Hass over an authenticated private connection. Do not forward unrelated chat history.
4. Hass turns the request into a typed draft. Missing or uncertain facts produce a focused question. Photos, transcripts, labels and quoted third-party text are evidence, not new authority to run commands.
5. Deterministic code validates the draft and prepares a readable summary plus private screenshot. The owner replies approve, revise or cancel in that same chat.
6. Approval is tied to sender, chat, change ID, exact revision/hash, base content revision and expiry. “Yes” can resolve only the single unambiguous pending draft; otherwise ask which one. An edited draft invalidates its old approval.
7. A single writer rechecks the base revision, applies an atomic content change, runs checks and switches the private preview to the checked result. It records the approved content change in Git without personal messages or participant data.
8. Hass sends an accurate result and screenshot. Persist the result before sending the reply so a restart or failed send cannot repeat the mutation.

Use explicit states such as received → needs-details → proposed → approved → validating → applied → verified. Also support rejected, expired, failed and reverted. Distinguish an applied change with a pending reply from an unapplied change. A partial failure must enter reconciliation, not blind retry.

## Editing tools and data contracts

| Tool family | Allowed inputs / behavior |
| --- | --- |
| Catalog | List/search by stable ID; draft add/update/hide/restore. Validate category, producer reference, description and image reference. Preserve sourcing evidence and held status. |
| Maker profiles | Draft name, bio, base location and source links. Label a maker's base separately from the product's farm of origin. Unsupported organic claims stay unapproved. |
| Hikes | Draft create/update/cancel/complete. Require exact date and local time with `America/Los_Angeles` timezone, meeting details and explicit RSVP setting. Validate positive capacity and current RSVP totals before lowering it. |
| Route data | Reuse documented trail data or request verification. Never fabricate a map, elevation profile, access permission or completed outing. |
| Website copy | Edit defined fields/slots for hours, introduction, photos and section copy. Escape markup and allowlist links. Layout/code changes follow a separate checked branch workflow. |
| Review/history | Show a draft, summary, screenshot or applied change; approve/reject/cancel; pause; propose a selective revert. |
| Community status | Return aggregate guest totals by event. Participant details require a separately justified permission; do not expose them in routine screenshots or logs. |

Do not accept shell commands, arbitrary paths, SQL, arbitrary browser actions or credentials as tool arguments. A user-facing request to “remove” a product means hide/archive by default, not erase its evidence. Do not let a change to a maker accidentally relabel all its products as organic or locally grown.

Keep canonical content outside the directly served directory if it contains internal evidence; emit only approved public fields and optimized assets into the site. Use a migration check proving all 170 existing active records, 26 maker profiles, source links and held exclusions are preserved. The two held cheese candidates require review of their recorded manufacturer concern, not a generic restore command.

## GitHub and concurrent work

- GitHub `main` is the shared source of truth. Agent Orange is a checkout/runtime, not an independent competing source.
- Start each task from current GitHub main; use `codex/<task>` branches and small reviewed commits. A branch or pull request is for builders; Michael reviews his content in Messages.
- Do not let Hermes code work and the Hass content writer race on one worktree. Give the writer an isolated worktree/branch and serialize application to the preview.
- Include a non-personal change ID and content diff in commits. Keep owner phone numbers, raw messages, approval records, original media, credentials and participant information in private runtime storage.
- Fail closed on stale revisions. Rebuild the draft against current content and reapprove changes that alter the approved result. Never force-push or overwrite unrelated Hermes work to resolve a conflict.
- Approval to apply a private content edit is not permission to publish publicly, buy services, notify subscribers or change account access.
- Undo is a new, conflict-checked inverse change. Do not reset the whole repository or restore a community database to undo a product edit.

## Mac bridge and private connectivity

Use a dedicated business-controlled Apple account and Mac login/profile. Michael must choose the actual Mac and sign in himself; ownership of a spare Mac does not authorize reading the current user's Messages database.

BlueBubbles is a candidate transport, not an Apple-provided bot API. It uses the Mac Messages app and exposes message operations/events. The compatibility spike must verify text, photo and actual iPhone voice-note attachments on the chosen supported macOS version. Leave SIP and other platform protections enabled; optional Private API features are out of scope.

Prefer a Mac-local adapter with outbound access to Agent Orange through authenticated SSH or an existing approved private network. Bind owner services to loopback; tunnel a private receiver if callbacks are needed. Do not open a public BlueBubbles/webhook port, weaken the existing site Host/Origin checks, or enable public Cloudflare/ngrok routing as a convenience.

Provider authentication can place secrets in query strings. Redact URLs and request headers; keep secrets only in a protected local secret store or environment file. Do not assume a webhook body authenticates its sender: receive locally and authenticate the forwarded envelope. Test impersonation, replay, unknown senders and edited message events. Do not backfill old messages as commands on first boot; record the approved start point and replay only unfinished recorded work.

The Mac must remain powered, connected and signed in appropriately. Record what happens after logout, sleep, reboot and a macOS update; a reboot may need a person to unlock/sign in. Do not weaken disk encryption or enable automatic login to hide that limitation. If voice attachments or private networking fail the spike, report the exact gap before promising support or switching to a paid/public bridge.

## Media, memory and privacy

- Accept only supported file types with size limits; inspect actual content, not just filename extensions. Reject unexpected documents/executables and path traversal.
- Keep originals privately with source IDs. Create optimized display copies, remove GPS metadata and avoid unnecessary faces, receipts or identifying details in the public image.
- Treat photo cleanup as presentation, not license to invent packaging, certifications, weights, farm names or ingredients. Ask when text is unreadable.
- Send only necessary owner content to the selected model service, under a business-approved account/budget and retention settings. No model provider is assumed provisioned.
- Store verified owner preferences/facts separately from raw chat. Record source and date, support correction/deletion, and do not treat repetition or model memory as proof.
- Agree retention periods before the owner trial. Private queues, media, model traces and approval records must be excluded from Git and backed up according to their purpose.
- Preserve newsletter/hiking consent boundaries. Updating a hike and sending an announcement are separate operations; no email delivery is currently connected.

## Acceptance and recovery tests

| Test | Required result |
| --- | --- |
| Owner requests add/edit/hide/restore | Correct item; approved version applied once; screenshot matches; no commerce fields/UI introduced |
| Ambiguous item, unreadable label, unclear voice/date | Clarifying question; no guessed mutation |
| Unknown sender, group message, outbound echo, replay | No website write and no unauthorized disclosure |
| Duplicate delivery, edited message, delayed “yes” | No duplicate write; approval cannot migrate to new content |
| Two simultaneous edits / Hermes change | Conflict detected; no lost update; reapproval when needed |
| Unsafe markup, paths or attachment | Rejected without execution or unintended file access |
| Hike reschedule/cancel/capacity below guest count | Existing RSVPs retained; invalid capacity rejected; no automatic participant email |
| Mac/network/model/Git failure before and after write | Durable state and accurate reply; reconcile rather than repeat; existing site keeps serving |
| Undo and recovery | Restore intended content change without undoing later work; isolated backup restore demonstrated |
| Website regression | All intended records/assets, sources, filtering and maps preserved; phone/desktop readability and keyboard use checked |
| Forms and privacy | Isolated fixture DB only; separate consents, duplicate/capacity protections and no participant leaks |

Write fresh results to a new report with date, commit, environment and limits. Existing QA JSON is historical evidence. Do not claim a physical iPhone test from browser emulation. For this documentation task, no runtime changes or fresh browser regression are required.

## Bridge research and open questions

Official sources checked October 30, 2026:

- [Apple: set up Messages on Mac](https://support.apple.com/en-au/guide/messages/ichte16154fb/mac): Apple accounts can use chosen reachable email addresses or phone numbers. An email-based assistant contact is the proposed initial route; SMS forwarding is a different setup.
- [BlueBubbles server overview](https://docs.bluebubbles.app/server): the bridge runs on macOS, reads Messages events and supports basic sends/attachments through AppleScript. Verify the actual release and macOS compatibility; do not use old recommended operating systems solely because the documentation names them.
- [BlueBubbles REST API and webhooks](https://docs.bluebubbles.app/server/developer-guides/rest-api-and-webhooks): the server offers authenticated requests and message event callbacks. Validate callback authentication and redact query-string secrets in our adapter.
- [BlueBubbles optional Private API](https://docs.bluebubbles.app/private-api/installation): enabling those extra features requires disabling SIP. We will not enable it; prove the needed workflow using basic capabilities.

Open before connection: chosen Mac model/macOS; business account/address and owner sender; required local permissions; bridge release and attachment behavior; private transport route; model credentials/budget; retention and support owner. None of these are prerequisites to implement/test the content tools with isolated fixtures.
