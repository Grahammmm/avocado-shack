# Going live: the steps only G and Michael can do

Plain words, in order. Everything is typed by G on AgentOrange unless it says otherwise. **Nobody else (no agent) holds the key, the GitHub or Cloudflare login, or the phone numbers.** If a "Check" fails, stop and do not go on; the site is not touched until step 7.

Before you start: runbook steps 1–19 are done (Mac forwarder, receiver and worker running, `approvals` still `hold`), a reply **picture** arrives on the phone, and the test battery has passed.

**1. Make the site-only key (G, AgentOrange).**
```
ssh-keygen -t ed25519 -N "" -C hass-site -f ~/.ssh/hass_site
printf 'Host github-avocadoman\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/hass_site\n  IdentitiesOnly yes\n' >> ~/.ssh/config
chmod 600 ~/.ssh/config; cat ~/.ssh/hass_site.pub
```
Check: one line starting `ssh-ed25519`. (If the key file exists, `ssh-keygen` asks before overwriting: answer no and tell the operator.)

**2. Give that key write access to the site repo only (G, GitHub in a browser).** `theavocadoman-site` → Settings → Deploy keys → Add deploy key. Title `hass-site`, paste the line, **tick Allow write access**. Then on AgentOrange: `ssh -T git@github-avocadoman`. Compare the fingerprint it shows with GitHub's published list before typing `yes`.
Check: it says `Hi Grahammmm/theavocadoman-site! You've successfully authenticated…` (exit code 1 is normal). If it says only `Hi Grahammmm!` it used the wrong key: stop.

**3. Two Cloudflare checks (G, Cloudflare dashboard; names may differ slightly).** Pages project for theavocadoman: production branch is `main` of `theavocadoman-site`. Switch **off** anything that rewrites pages: Email Address Obfuscation, Rocket Loader, Auto Minify, Web Analytics auto-install. (If they stay on, Hass cannot confirm a change and every publish ends "I can't see it there yet".)

**4. Get the site copy and prove nothing rewrites it (G).**
```
git clone git@github-avocadoman:Grahammmm/theavocadoman-site.git ~/.local/share/hass/theavocadoman-site
git -C ~/.local/share/hass/theavocadoman-site config user.name 'Hass'
git -C ~/.local/share/hass/theavocadoman-site config user.email 'hass@users.noreply.github.com'
git -C ~/.local/share/hass/theavocadoman-site show HEAD:index.html | sha256sum
curl -s https://theavocadoman.com/ | sha256sum
```
Check: the two long numbers are identical. If not, go back to step 3.

**5. Say who the owners are and which site (G; edit privately, never paste these into chat).**
* State file `~/.local/state/hass/state/config.json`, inside `settings` (Mike's address is his iMessage email or +1 number; G's is G's own):
  `"ownerSenders": ["<Mike address>"], "ownerChat": "iMessage;-;<Mike address>", "gSenders": ["<G address>"], "gChat": "iMessage;-;<G address>", "gIsOwner": true, "liveSite": "theavocadoman.com", "approvalNeedsCode": true`
* Host file `~/.local/state/hass/host/host.json`: add (absolute paths, `<home>` = your home folder; keep the file private, mode 600):
  `"release": {"siteCheckout": "<home>/.local/share/hass/theavocadoman-site", "siteRemote": "git@github-avocadoman:Grahammmm/theavocadoman-site.git", "liveUrl": "https://theavocadoman.com", "stopFile": "<home>/.config/hass/STOP", "dailyCap": 10, "minIntervalSeconds": 120, "verifyMinutes": 15}`
* On the Mac, in the forwarder `config.json`, set `ownerChat` to Mike's chat and add `gChat` as G's chat (same `iMessage;-;<address>` form), then `launchctl kickstart -k gui/$(id -u)/com.avocadoshack.hass-forwarder`.
* Michael first texts the business number once ("hi") so his chat exists; G does the same.
Check: `cd ~/.local/share/hass/runtime && python3 hass/host.py check --host ~/.local/state/hass/host/host.json` prints `"result": "ok"`. A text from any other number gets no answer and starts nothing.

**6. First publish: bring the site level with Hass (G).**
```
cd ~/.local/share/hass/runtime
python3 hass/publish_live.py adopt --host ~/.local/state/hass/host/host.json
```
`adopted` → go to step 7. `differs` → (the site's one commit is older than today's code, so expect this):
```
python3 hass/publish_live.py adopt --from-remote --host ~/.local/state/hass/host/host.json
python3 hass/publish_live.py baseline --host ~/.local/state/hass/host/host.json
python3 hass/sitegen.py --publish ~/hass-preview
python3 -m http.server 8089 --bind 127.0.0.1 --directory ~/hass-preview
```
Look at the preview in a browser (SSH-forward port 8089). **This publishes everything now on avocado-shack main that the site does not have.** Only if the privacy list printed by `baseline` is empty and the pages look right:
`python3 hass/publish_live.py baseline --host ~/.local/state/hass/host/host.json --confirm <manifest from the preview>`, then `rm -rf ~/hass-preview`.
Check: `python3 hass/publish_live.py status --host ~/.local/state/hass/host/host.json` shows no open release; `https://theavocadoman.com` looks right.

**7. Switch on (G).**
```
python3 hass/host.py mode live --host ~/.local/state/hass/host/host.json && systemctl --user restart hass-worker
```
Check: it prints `"approvals": "live"`; `systemctl --user is-active hass-worker` says `active`. **To switch back at any time:** `python3 hass/host.py mode private --host ~/.local/state/hass/host/host.json && systemctl --user restart hass-worker`.

**8. G tries it on G's own phone first.** Send one small description change, reply `yes <code>`. Expect "Saved…", then within a few minutes "Your change is on the website now." with a picture; look at the page; then send `undo`, `yes <code>` and see it go back. Anything else: switch back (step 7), tell the operator.

**9. Michael.** After G says go: send one small change in your own words, check what Hass says it will do, reply `yes <code>`. You get "Saved", then "Your change is on the website now." with a picture; open theavocadoman.com and look. If it is wrong, text `undo` then `yes <code>`. Hass will say plainly if it cannot put something on the website from chat; Graham sees those.

**If something goes wrong:** `touch ~/.config/hass/STOP` stops all publishing at once. Taking the last change off the site: `cd ~/.local/share/hass/runtime && python3 hass/publish_live.py revert-last --host ~/.local/state/hass/host/host.json`, then the same `status` a minute later.
