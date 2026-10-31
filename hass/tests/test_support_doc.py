"""RF0935-6 (H17/H19): docs/hass/SUPPORT.md documents exactly the ids hass/health.py emits (stdlib, offline)."""
import ast
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEALTH, DOC = ROOT / "hass" / "health.py", ROOT / "docs" / "hass" / "SUPPORT.md"


def _calls(nodes):
    return [n for top in nodes for n in ast.walk(top) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name) and n.func.id == "_problem" and n.args]


def emitted_ids(source: str) -> set:
    """String first args of _problem(...) plus the first strings of tuple literals a for loop feeds to _problem(var, ...)."""
    tree = ast.parse(source)
    ids = {c.args[0].value for c in _calls([tree]) if isinstance(c.args[0], ast.Constant) and isinstance(c.args[0].value, str)}
    for loop in (n for n in ast.walk(tree) if isinstance(n, ast.For) and isinstance(n.iter, (ast.Tuple, ast.List))):
        var = loop.target.elts[0] if isinstance(loop.target, ast.Tuple) and loop.target.elts else loop.target
        if not isinstance(var, ast.Name) or not any(isinstance(c.args[0], ast.Name) and c.args[0].id == var.id
                                                   for c in _calls(loop.body)):
            continue
        for item in loop.iter.elts:
            first = item.elts[0] if isinstance(item, ast.Tuple) and item.elts else item
            if isinstance(first, ast.Constant) and isinstance(first.value, str): ids.add(first.value)
    return ids


def documented_ids(doc: str) -> set:
    return set(re.findall(r"^### `([^`]+)`\s*$", doc, re.M))


def mismatches(source: str, doc: str) -> list:
    emitted, documented = emitted_ids(source), documented_ids(doc)
    return ([f"undocumented: {i}" for i in sorted(emitted - documented)]
            + [f"stale heading: {i}" for i in sorted(documented - emitted)])


def bad_commands(doc: str, root: Path = ROOT) -> list:
    return [p for p in re.findall(r"python3 (hass/[\w./-]+)", doc) if not (root / p).is_file()]


def private_data(doc: str) -> list:
    return [m.group(0) for m in re.finditer(r"@|\d{7,}|https?://\S*", doc)]


LOOP = '''
for check, table in (("a-stuck", "x"), ("b-stuck", "y")):
    if table: problems.append(_problem(check, "1"))
for other, table in (("c-stuck", "x"),):
    _problem("fixed", other)
'''


class SupportDocTest(unittest.TestCase):
    def test_real_files_agree(self):
        self.assertEqual(mismatches(HEALTH.read_text("utf-8"), DOC.read_text("utf-8")), [])
        self.assertGreaterEqual(documented_ids(DOC.read_text("utf-8")), {"state", "inbox-stuck", "paused", "conversation"})

    def test_undocumented_id_is_named(self):
        source = HEALTH.read_text("utf-8") + '\n_problem("disk-full", "0")\n'
        self.assertEqual(mismatches(source, DOC.read_text("utf-8")), ["undocumented: disk-full"])

    def test_stale_heading_is_named(self):
        doc = DOC.read_text("utf-8") + "\n### `old-check`\n"
        self.assertEqual(mismatches(HEALTH.read_text("utf-8"), doc), ["stale heading: old-check"])

    def test_loop_ids_only_when_loop_variable_reaches_problem(self):
        self.assertEqual(emitted_ids(LOOP), {"a-stuck", "b-stuck", "fixed"})

    def test_non_literal_first_argument_is_ignored(self):
        self.assertEqual(emitted_ids('name = "x"\n_problem(name, "d")\n_problem(f"{name}", "d")\n_problem()\n'), set())

    def test_heading_wording_must_be_exact(self):
        self.assertEqual(documented_ids("### state\n## `settings`\n### `seen` extra\n#### `paused`\n"), set())

    def test_command_paths_must_exist(self):
        self.assertEqual(bad_commands("run `python3 hass/nope.py --state DIR`\npython3 hass/health.py"), ["hass/nope.py"])
        self.assertEqual(bad_commands(DOC.read_text("utf-8")), [])
        self.assertIn("python3 hass/health.py", DOC.read_text("utf-8"))

    def test_no_private_data(self):
        self.assertEqual(private_data(DOC.read_text("utf-8")), [])
        self.assertEqual(len(private_data("mail a@b, call 5551234567, see http://x")), 3)


if __name__ == "__main__":
    unittest.main()
