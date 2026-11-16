#!/usr/bin/env python3
"""AUDINV-FIX-041: reconcile the fixed 76 PROPOSED/UNCLEAR Avocado decision IDs.

Local-only, offline, stdlib-only report tool. It records what the files say and
never decides approve/deny, edits state/queue/ledger, or revives held units.
  --self-test                         run the embedded synthetic unittest cases
  --snapshot AUDIT STATE LOG APPLIED MAP   read those files (read-only, explicit
                                      paths) and write SOURCES.json in the package
  --emit TSV --sources SOURCES.json   derive the TSV from SOURCES.json
  --check TSV --sources SOURCES.json  validate the TSV against SOURCES.json
Paths for --sources/--emit/--check resolve beneath this package root.
"""
import argparse, hashlib, json, os, re, sys, unittest

ROOT = os.path.dirname(os.path.realpath(__file__))
COLS = ["id", "original_class", "current_status", "state_as_of", "recorded_decision",
        "decision_date", "decision_source", "scope_match", "conflicts", "disposition",
        "missing_evidence"]
DISPOSITIONS = {"HOLD", "DENIED", "CUT-RECORDED", "RELEASE-RECORDED"}
ID_RE = re.compile(r"\b(AV|RF)(\d{4})-(\d\d)((?:/\d\d)*)\b")
GROUP_LINES = (1635, 1896, 1930, 1931, 1565, 1580)
ATTEMPTED_IO = []  # recording-only: disallowed I/O attempts land here, never executed


class SourceError(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def ids_in(text):
    """Exact IDs in a log line; expands the 'AV1922-08/09/10' shorthand."""
    out = set()
    for m in ID_RE.finditer(text):
        out.add("%s%s-%s" % (m.group(1), m.group(2), m.group(3)))
        for extra in filter(None, m.group(4).split("/")):
            out.add("%s%s-%s" % (m.group(1), m.group(2), extra))
    return out


def safe_path(rel):
    """Resolve beneath ROOT; reject absolute, traversal, symlinks (recorded, not opened)."""
    if os.path.isabs(rel) or ".." in rel.replace("\\", "/").split("/"):
        ATTEMPTED_IO.append(rel)
        raise SourceError("path escapes package root: %r" % rel)
    p = os.path.join(ROOT, rel)
    if os.path.islink(p) or os.path.realpath(p) != os.path.normpath(p) and os.path.exists(p):
        ATTEMPTED_IO.append(rel)
        raise SourceError("symlink path refused: %r" % rel)
    return p


def tsv_cell(v):
    s = re.sub(r"[\t\r\n]+", " ", str(v)).strip()
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s


def _seg(text, pat):
    m = re.search(pat, text)
    return m.group(1) if m else ""


def classify(e, groups):
    """One source entry -> TSV row dict. Pure; no recommendation is read as a decision."""
    st = e.get("state") or {}
    status = st.get("status", "ABSENT")
    why = " ".join(x for x in (st.get("why"), st.get("note")) if x)
    log_hits = [h for h in e.get("log_exact", [])]
    decision, date, src, scope, disp = [], "", [], "NONE", "HOLD"
    conflicts, missing = [], []
    denied = [h for h in log_hits if e["id"] in ids_in(_seg(h["text"], r"keeping the \d+ DENIED \(([^)]*)\)"))]
    released = [h for h in log_hits if e["id"] in ids_in(_seg(h["text"], r"Tranche 1: released ([^(]*)"))]
    if denied:
        h = denied[0]
        decision.append("G kept DENIED (log line %d)" % h["line"])
        date, scope, disp = h["date"], "EXACT_ID_LOG", "DENIED"
        src.append("G-DECISIONS.log:%d" % h["line"])
        if status in ("merged", "pr", "queued"):
            conflicts.append("recorded denial but state=%s (denial stays)" % status)
    elif released:
        h = released[0]
        decision.append("G released this exact ID, lifting hold (tranche 1, lane->sonnet-coder); a hold lift, not a feature approval")
        date, scope, disp = h["date"], "EXACT_ID_LOG", "RELEASE-RECORDED"
        src.append("G-DECISIONS.log:%d" % h["line"])
    elif e.get("map") and e["map"].get("recommendation") == "CUT" and (why.startswith("G 2026-11-15 CUT")):
        decision.append("G CUT all 62 per MILESTONE-MAP-1 (log line 1930); this ID is a CUT row in the map and state records the cut")
        date, scope, disp = "2026-11-15", "EXACT_ID_VIA_MAP_REF_LOG_1930", "CUT-RECORDED"
        src.append("G-DECISIONS.log:1930; reports/milestone-map-1/MILESTONE-MAP.tsv:%d" % e["map"]["line"])
        if status in ("merged", "pr", "queued"):
            conflicts.append("recorded CUT but state=%s" % status)
    else:
        if "APPROVED 2026-11-07" in why:
            decision.append("state note 'G APPROVED 2026-11-07'; log 1635 approves a group ('Avocado site 9') with no ID list")
            date, scope = "2026-11-07", "STATE_NOTE_AND_GROUP_LOG_1635_NO_ID_LIST"
            src += ["modes/unit-state.json:%s.why" % e["id"], "G-DECISIONS.log:1635"]
            missing.append("no per-ID approval record naming this ID")
            if e.get("applied"):
                conflicts.append("approval note (11-07) post-dates APPLIED hold (11-05, log 1565); supersession by ID unrecorded")
        elif "HOLD" in why or "held for G" in why or "dropped" in why:
            m = re.search(r"G (\d{4}-\d\d-\d\d)", why)
            decision.append("state note: " + why[:160])
            date = m.group(1) if m else ""
            scope = "STATE_NOTE_ONLY"
            src.append("modes/unit-state.json:%s.why" % e["id"])
            missing.append("no per-ID log line; state note is operator-written")
            if "HASS-LIVE-AUDIT-1" in why:
                decision.append("hold generally lifted by log 1896, no per-ID release for this ID")
                src.append("G-DECISIONS.log:1896")
            if "dropped" in why:
                conflicts.append("state says dropped but APPLIED json lists it held and status=%s" % status)
        else:
            missing.append("no per-ID decision record found")
            scope = "NONE"
        if e.get("applied"):
            decision.append("listed in QUEUE-AUDIT-APPLIED.json %s (2026-11-05 audit hold, log 1565)" % e["applied"])
            src.append("reports/QUEUE-AUDIT-APPLIED.json")
            date = date or "2026-11-05"
            scope = scope if scope != "NONE" else "APPLIED_JSON_EXACT_ID_HOLD_ONLY"
        if status == "merged" and ("HOLD" in why or "held for G" in why or "dropped" in why):
            conflicts.append("state=merged while recorded hold/drop stands; merge is execution, not authority")
        if status == "merged" and not decision:
            missing.append("merged is historical execution, not authorization")
        missing.append("no G approve/deny for this feature by exact ID")
    if e["cls"] not in ("PROPOSED", "UNCLEAR"):
        raise SourceError("bad class %r" % e["cls"])
    if conflicts and disp not in ("DENIED",):
        disp = "HOLD"
    row = {"id": e["id"], "original_class": e["cls"], "current_status": status,
           "state_as_of": groups["state_as_of"], "recorded_decision": "; ".join(decision) or "none recorded",
           "decision_date": date, "decision_source": "; ".join(src) or "none", "scope_match": scope,
           "conflicts": "; ".join(conflicts) or "none", "disposition": disp,
           "missing_evidence": "; ".join(dict.fromkeys(missing)) or "none"}
    return row


def load_sources(rel):
    try:
        d = json.loads(open(safe_path(rel)).read(), object_pairs_hook=_nodup)
    except (OSError, ValueError) as ex:
        raise SourceError("sources unreadable: %s" % ex)
    if d.get("schema_version") != 1 or not isinstance(d.get("entries"), list):
        raise SourceError("unknown schema")
    return d


def _nodup(pairs):
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate key")
    return dict(pairs)


def frozen_ids(d):
    ids = [e["id"] for e in d["entries"]]
    if len(ids) != len(set(ids)):
        raise SourceError("duplicate IDs")
    for i in ids:
        if not re.fullmatch(r"(AV|RF)\d{4}-\d\d", i):
            raise SourceError("invalid ID %r" % i)
    counts = {c: sum(1 for e in d["entries"] if e["cls"] == c) for c in ("PROPOSED", "UNCLEAR")}
    if d.get("expected") and (len(ids) != d["expected"]["total"] or counts != d["expected"]["classes"]):
        raise SourceError("ID count %d %s != expected" % (len(ids), counts))
    return ids


def emit_rows(d):
    frozen_ids(d)
    return [classify(e, d["groups"]) for e in d["entries"]]


def render(rows):
    return "\n".join(["\t".join(COLS)] + ["\t".join(tsv_cell(r[c]) for c in COLS) for r in rows]) + "\n"


def check_text(text, d):
    ids = frozen_ids(d)
    lines = text.rstrip("\n").split("\n")
    if lines[0].split("\t") != COLS:
        raise SourceError("bad header")
    got = [l.split("\t") for l in lines[1:]]
    if any(len(g) != len(COLS) for g in got):
        raise SourceError("bad column count")
    if [g[0] for g in got] != ids:
        raise SourceError("IDs missing/extra/duplicate/out of order vs frozen set")
    for g in got:
        if g[COLS.index("disposition")] not in DISPOSITIONS:
            raise SourceError("bad disposition for %s" % g[0])
    if render(emit_rows(d)) != text:
        raise SourceError("rows differ from those derived from SOURCES.json")
    return len(ids)


def snapshot(audit, state, log, applied, mapf):
    raw = {k: open(p, "rb").read() for k, p in dict(audit=audit, state=state, log=log, applied=applied, map=mapf).items()}
    arows = raw["audit"].decode().split("\n")
    st = json.loads(raw["state"])
    loglines = raw["log"].decode().split("\n")
    ap = json.loads(raw["applied"])
    mp = {}
    for n, l in enumerate(raw["map"].decode().split("\n"), 1):
        f = l.split("\t")
        if n > 1 and len(f) > 5:
            mp[f[0]] = {"line": n, "recommendation": f[5], "action": f[8] if len(f) > 8 else ""}
    applied_keys = {k: set(v) for k, v in ap.items() if isinstance(v, list)}
    entries = []
    for n in range(59, 215):
        f = arows[n - 1].split("\t")
        if f[1] not in ("PROPOSED", "UNCLEAR"):
            continue
        i = f[0]
        s = st.get(i, {})
        hits = []
        for ln in range(1, len(loglines) + 1):
            if i in ids_in(loglines[ln - 1]):
                t = loglines[ln - 1]
                hits.append({"id": i, "line": ln, "date": t[:10] if re.match(r"\d{4}-", t) else t[2:12], "text": t})
        entries.append({"id": i, "cls": f[1], "audit_line": n, "audit_evidence": f[2], "audit_recommendation": f[3],
                        "state": {k: s[k] for k in ("status", "why", "note", "card", "at") if k in s},
                        "log_exact": hits, "applied": sorted(k for k, v in applied_keys.items() if i in v),
                        "map": mp.get(i)})
    return {"schema_version": 1, "expected": {"total": 76, "classes": {"PROPOSED": 48, "UNCLEAR": 28}},
            "groups": {"state_as_of": "modes/unit-state.json sha256 " + sha(raw["state"]) + " read at snapshot time"},
            "group_log_lines": {str(n): loglines[n - 1] for n in GROUP_LINES},
            "digests": {"QUEUE-AUDIT.tsv": sha(raw["audit"]), "G-DECISIONS.log": sha(raw["log"]),
                        "unit-state.json": sha(raw["state"]), "QUEUE-AUDIT-APPLIED.json": sha(raw["applied"]),
                        "MILESTONE-MAP.tsv": sha(raw["map"])},
            "missing_coverage": ["units_all.tsv not present in agent-work (queue state read from modes/unit-state.json)",
                                 "no per-ID record for the 11-07 'Avocado site 9' approval group",
                                 "AV1922-09/10 are in the 1896 denial but outside the 76"],
            "entries": entries}


# ---- embedded local-only tests (python3 candidate.py --self-test) ----
def _fx():
    return json.load(open(os.path.join(ROOT, "fixtures.json")), object_pairs_hook=_nodup)


class Cases(unittest.TestCase):
    def setUp(self):
        self.fx = _fx()

    def src(self, entries):
        return {"schema_version": 1, "groups": {"state_as_of": "fx"}, "entries": entries}

    def test_exact_76_ids_no_missing_extra_or_duplicate(self):
        ents = self.fx["entries"]
        d = self.src(ents)
        d["expected"] = {"total": len(ents), "classes": {"PROPOSED": 4, "UNCLEAR": 2}}
        self.assertEqual(len(frozen_ids(d)), len(ents))
        d["expected"]["total"] += 1
        with self.assertRaises(SourceError):
            frozen_ids(d)
        with self.assertRaises(SourceError):
            frozen_ids(self.src(ents + [ents[0]]))
        text = render(emit_rows(self.src(ents)))
        with self.assertRaises(SourceError):
            check_text(text.replace(ents[1]["id"], "AV9999-99"), self.src(ents))

    def test_proposed_recommendation_not_an_owner_decision(self):
        r = {x["id"]: x for x in emit_rows(self.src(self.fx["entries"]))}["AV9001-01"]
        self.assertEqual(r["disposition"], "HOLD")
        self.assertEqual(r["scope_match"], "NONE")

    def test_broad_pick_does_not_override_exact_denial(self):
        r = {x["id"]: x for x in emit_rows(self.src(self.fx["entries"]))}["AV1922-08"]
        self.assertEqual(r["disposition"], "DENIED")
        self.assertIn("EXACT_ID_LOG", r["scope_match"])
        e = [dict(x) for x in self.fx["entries"]]
        e[[x["id"] for x in e].index("AV1922-08")]["state"] = {"status": "merged", "why": "G APPROVED 2026-11-07"}
        r2 = {x["id"]: x for x in emit_rows(self.src(e))}["AV1922-08"]
        self.assertEqual(r2["disposition"], "DENIED")
        self.assertNotEqual(r2["conflicts"], "none")

    def test_conflicting_or_missing_decision_stays_hold(self):
        rows = {x["id"]: x for x in emit_rows(self.src(self.fx["entries"]))}
        self.assertEqual(rows["AV9001-02"]["disposition"], "HOLD")
        self.assertIn("merge is execution", rows["AV9001-02"]["conflicts"])
        self.assertEqual(rows["AV9001-03"]["disposition"], "HOLD")
        self.assertIn("no per-ID", rows["AV9001-03"]["missing_evidence"])
        self.assertEqual(rows["AV9001-04"]["disposition"], "HOLD")
        self.assertEqual(rows["AV9001-05"]["disposition"], "RELEASE-RECORDED")

    def test_merged_state_does_not_prove_authority_and_tsv_escapes_cells(self):
        rows = {x["id"]: x for x in emit_rows(self.src(self.fx["entries"]))}
        self.assertEqual(rows["AV9001-03"]["current_status"], "merged")
        self.assertEqual(rows["AV9001-03"]["disposition"], "HOLD")
        self.assertEqual(tsv_cell("a\tb\nc"), "a b c")
        self.assertEqual(tsv_cell("=1+1"), "'=1+1")
        line = render([dict(rows["AV9001-03"], recorded_decision="x\ty\n=z")]).split("\n")[1]
        self.assertEqual(len(line.split("\t")), len(COLS))

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        del ATTEMPTED_IO[:]
        for bad in ("../x.json", "/etc/passwd", "a/../../b"):
            with self.assertRaises(SourceError):
                safe_path(bad)
        self.assertEqual(len(ATTEMPTED_IO), 3)
        with self.assertRaises(SourceError):
            frozen_ids(self.src([{"id": "bad id", "cls": "PROPOSED"}]))
        self.assertEqual(ids_in("keeping the 3 DENIED (AV1922-08/09/10)"), {"AV1922-08", "AV1922-09", "AV1922-10"})
        self.assertEqual(ids_in("AV19220-08"), set())
        with self.assertRaises(SourceError):
            check_text("id\n", self.src(self.fx["entries"]))
        self.assertTrue(os.path.isdir(ROOT))


def main(argv):
    ap = argparse.ArgumentParser(prog="candidate.py", description=__doc__)
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--snapshot", nargs=5, metavar=("AUDIT", "STATE", "LOG", "APPLIED", "MAP"))
    ap.add_argument("--emit")
    ap.add_argument("--check")
    ap.add_argument("--sources")
    a = ap.parse_args(argv)
    try:
        if a.self_test:
            r = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cases))
            return 0 if r.wasSuccessful() else 1
        if a.snapshot:
            d = snapshot(*a.snapshot)
            frozen_ids(d)
            open(safe_path("SOURCES.json"), "w").write(json.dumps(d, indent=1, sort_keys=True) + "\n")
            print("SOURCES.json written: %d entries" % len(d["entries"]))
            return 0
        if (a.emit or a.check) and a.sources:
            d = load_sources(a.sources)
            if a.emit:
                open(safe_path(a.emit), "w").write(render(emit_rows(d)))
                print("wrote", a.emit)
            if a.check:
                n = check_text(open(safe_path(a.check)).read(), d)
                print("CHECK OK: %d rows, one per frozen ID; no action authorized" % n)
            return 0
    except (SourceError, OSError, KeyError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 2
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
