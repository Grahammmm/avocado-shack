"""Scratch run of the repo's local community server (storefront-mockup/community-server.py) on loopback.
Uses a SCRATCH config with one SYNTHETIC hike and a SCRATCH sqlite file. Never touches community-data/.
Seeds 4 synthetic seats through the server's own POST (no real person). Usage: serve_scratch_api.py PORT [seats]"""
import json, os, runpy, sys, threading, time, urllib.request, datetime
from pathlib import Path

ws = Path(os.environ.get("HERMES_KANBAN_WORKSPACE", "."))
repo = Path("/home/user/repos/avocado-shack/.worktrees/t_e5d28414")
port = int(sys.argv[1]); seats = int(sys.argv[2]) if len(sys.argv) > 2 else 4
cfg = json.loads((repo / "storefront-mockup/community.json").read_text())
start = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=6)).astimezone().replace(hour=9, minute=0, second=0, microsecond=0)
cfg["events"] = [{
    "id": "scratch-hike", "title": "Scratch sample hike (not a real outing)", "startsAt": start.isoformat(),
    "timezone": "America/Los_Angeles", "status": "scheduled", "meetingPoint": "Scratch trailhead",
    "meetTime": "8:45 am", "walkTime": "9:00 am", "returnTime": "Around noon", "difficulty": "Moderate",
    "distance": "4 miles", "duration": "About 2 hours", "bring": "Water and a layer",
    "description": "Synthetic hike used only to render the page for the HIKEPAGE-1 design report.",
    "rsvpEnabled": True, "capacity": 6, "trailId": "idea-point-buchon"}]
(ws / "scratch-community.json").write_text(json.dumps(cfg))
db = ws / "scratch-community.sqlite3"
if db.exists(): db.unlink()
os.environ["AVOSHACK_COMMUNITY_CONFIG"] = str(ws / "scratch-community.json")
os.environ["AVOSHACK_COMMUNITY_DB"] = str(db)

def seed():
    time.sleep(2)
    for i in range(seats):
        body = json.dumps({"eventId": "scratch-hike", "name": f"Synthetic Guest {i+1}", "email": f"synthetic{i+1}@example.invalid", "partySize": 1}).encode()
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/community/rsvps", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"})
        try: urllib.request.urlopen(req, timeout=5).read()
        except Exception as e: print("seed failed", e, flush=True)
threading.Thread(target=seed, daemon=True).start()
sys.argv = ["community-server.py", "--port", str(port)]
runpy.run_path(str(repo / "storefront-mockup/community-server.py"), run_name="__main__")
