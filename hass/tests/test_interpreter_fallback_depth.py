"""RF1315-12: FallbackInterpreter refuses a nested FallbackInterpreter in either slot (one retry, never three attempts).
Fake interpreters only: no model, no socket. Run: python3 -B -m unittest hass.tests.test_interpreter_fallback_depth -q
"""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from hass.interpreter_local import FallbackInterpreter

REFUSAL = "interpreters must not have a fallback of their own"


class Fake:
    def __init__(self, result, last_error=None, backend="x"):
        self.result, self.last_error, self.last_backend, self.calls = result, last_error, backend, []

    def interpret(self, *args, **kw):
        self.calls.append((args, kw))
        return self.result


class Sub(FallbackInterpreter):
    pass


def ok(result):
    return isinstance(result, dict) and "question" in result


class FallbackDepthTests(unittest.TestCase):
    def pair(self):
        a, b = Fake({"question": "a"}), Fake({"question": "b"})
        return a, b, FallbackInterpreter(a, b, ok)

    def refused(self, primary, fallback):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(ValueError) as cm:
            FallbackInterpreter(primary, fallback, ok)
        self.assertEqual(str(cm.exception), REFUSAL)
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_nested_fallback_is_refused_before_any_transport(self):
        a, b, inner = self.pair()
        c = Fake({"question": "c"})
        self.refused(c, inner)
        self.assertEqual([a.calls, b.calls, c.calls], [[], [], []])

    def test_nested_primary_is_refused_before_any_transport(self):
        a, b, inner = self.pair()
        c = Fake({"question": "c"})
        self.refused(inner, c)
        self.assertEqual([a.calls, b.calls, c.calls], [[], [], []])

    def test_wrapper_subclasses_cannot_bypass_admission(self):
        a, b = Fake({"question": "a"}), Fake({"question": "b"})
        sub = Sub(a, b, ok)
        c = Fake({"question": "c"})
        self.refused(sub, c)
        self.refused(c, sub)
        self.assertEqual([a.calls, b.calls, c.calls], [[], [], []])

    def test_old_diagnostic_comes_first_for_invalid_arguments(self):
        _, _, inner = self.pair()
        with self.assertRaises(ValueError) as cm:
            FallbackInterpreter(inner, object(), ok)
        self.assertNotEqual(str(cm.exception), REFUSAL)

    def test_flat_pair_keeps_one_or_two_calls_and_metadata(self):
        a, b, w = self.pair()
        self.assertEqual(w.interpret("t", None), {"question": "a"})
        self.assertEqual((len(a.calls), len(b.calls), w.last_fallback), (1, 0, False))
        a, b = Fake(None, last_error="http-500"), Fake({"question": "b"}, backend="ollama")
        w = FallbackInterpreter(a, b, ok)
        self.assertEqual(w.interpret("t", None), {"question": "b"})
        self.assertEqual((len(a.calls), len(b.calls), w.last_fallback, w.last_primary_error, w.last_backend), (1, 1, True, "http-500", "ollama"))
        a, b = Fake(None, last_error="http-500"), Fake({"error": 1}, last_error="http-503")
        w = FallbackInterpreter(a, b, ok)
        w.interpret("t", None)
        self.assertEqual((len(a.calls), len(b.calls), w.last_error), (1, 1, "http-503"))

    def test_plain_duck_backend_and_shared_instance_stay_compatible(self):
        shared = Fake(None, last_error="e")
        shared.fallback = "unrelated"
        w = FallbackInterpreter(shared, shared, ok)
        w.interpret("t", None)
        self.assertEqual(len(shared.calls), 2)

    def test_flat_context_forwarding_and_final_invalid_object_are_unchanged(self):
        a, b = Fake(None, last_error="e"), Fake({"not": "contract"})
        w = FallbackInterpreter(a, b, ok)
        res = w.interpret("hi", {"p": 1}, ["n"], {"al": 1}, sent_at="S", recent=["r"])
        self.assertEqual(res, {"not": "contract"})
        self.assertEqual(b.calls, [(("hi", {"p": 1}, ["n"], {"al": 1}), {"sent_at": "S", "recent": ["r"]})])


if __name__ == "__main__":
    unittest.main()
