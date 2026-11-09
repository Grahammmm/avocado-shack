"""Scratch-only check against the loopback scratch server (synthetic names, scratch sqlite). Never the real store.
2 seats are left of 6. Fire 8 concurrent one-seat RSVPs: exactly 2 must succeed, 6 must be refused."""
import json, sys, threading, urllib.request, urllib.error
port = int(sys.argv[1]); results = []
def post(i, party=1):
    body = json.dumps({"eventId": "scratch-hike", "name": f"Race Guest {i}", "email": f"race{i}@example.invalid", "partySize": party}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/community/rsvps", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
    try:
        r = urllib.request.urlopen(req, timeout=10); results.append((i, r.status, json.loads(r.read()).get("message", "")[:40]))
    except urllib.error.HTTPError as e:
        results.append((i, e.code, json.loads(e.read()).get("error", "")[:60]))
ts = [threading.Thread(target=post, args=(i,)) for i in range(8)]
[t.start() for t in ts]; [t.join() for t in ts]
print(sorted(results))
ok = sum(1 for r in results if r[1] == 200)
data = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/community").read())
e = data["events"][0]
print("succeeded", ok, "confirmedGuests", e["confirmedGuests"], "remaining", e["remaining"], "keys", sorted(e.keys()))
post(99, 2); print(results[-1])
