"""RF2340-12: a raising final (second) interpreter returns the fixed failure with this call's metadata."""
import contextlib
import io
import json
import unittest
from unittest import mock

from hass.interpreter_local import FAILED, FallbackInterpreter

CANARY = "SYNTHETIC-EXCEPTION-CANARY"
GOOD = {"question": "Which day?"}
FIELDS = ("last_error", "last_backend", "last_fallback", "last_primary_error", "last_seconds")


class Backend:
    """Plain recording backend: each call pops the next step (a result, or an exception to raise)."""

    def __init__(self, name, *steps, error=None):
        self.steps, self.calls, self.last_error = list(steps), [], error
        if name is not None:
            self.last_backend = name

    def interpret(self, *args, **kw):
        self.calls.append((args, kw))
        step = self.steps.pop(0)
        if isinstance(step, BaseException):
            raise step
        result, self.last_error = step
        return result


def valid(result):
    return isinstance(result, dict) and len(result) == 1


def meta(w):
    return {f: getattr(w, f) for f in FIELDS}


class FinalExceptionCase(unittest.TestCase):
    def test_raising_final_backend_returns_fixed_failure_once(self):
        for exc in (RuntimeError(CANARY), ValueError(CANARY), OSError(CANARY)):
            with self.subTest(exc=type(exc).__name__):
                first = Backend("openai", ({"unsupported": FAILED}, "timeout"))
                second = Backend("ollama", exc, error="stale-code")
                w = FallbackInterpreter(first, second, valid)
                self.assertEqual(w.interpret("hi", None), {"unsupported": FAILED})
                self.assertEqual((w.last_error, w.last_backend, w.last_fallback, w.last_primary_error),
                                 ("error", "ollama", True, "timeout"))
                self.assertEqual((len(first.calls), len(second.calls)), (1, 1))

    def test_final_exception_replaces_previous_success_metadata(self):
        first = Backend("openai", (GOOD, None), ({"unsupported": FAILED}, "timeout"))
        second = Backend("ollama", RuntimeError(CANARY))
        w = FallbackInterpreter(first, second, valid)
        with mock.patch("hass.interpreter_local.time.monotonic", side_effect=[10.0, 10.0, 20.0, 21.5]):
            self.assertIs(w.interpret("one", None), GOOD)
            self.assertEqual(meta(w), {"last_error": None, "last_backend": "openai", "last_fallback": False,
                                       "last_primary_error": None, "last_seconds": 0.0})
            self.assertEqual(w.interpret("two", None), {"unsupported": FAILED})
        self.assertEqual(meta(w), {"last_error": "error", "last_backend": "ollama", "last_fallback": True,
                                   "last_primary_error": "timeout", "last_seconds": 1.5})

    def test_first_exception_then_final_exception_keeps_both_fixed_codes(self):
        first, second = Backend("openai", RuntimeError(CANARY)), Backend("ollama", ValueError(CANARY))
        w = FallbackInterpreter(first, second, valid)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = w.interpret("hi", None)
        self.assertEqual(result, {"unsupported": FAILED})
        self.assertEqual((w.last_error, w.last_primary_error, w.last_fallback), ("error", "error", True))
        self.assertEqual(len(first.calls) + len(second.calls), 2)
        self.assertNotIn(CANARY, out.getvalue() + err.getvalue() + json.dumps(result) + json.dumps(meta(w)))

    def test_recovery_after_raised_final_clears_failure_fields(self):
        other = {"question": "Which town?"}
        first = Backend("openai", (None, "timeout"), (GOOD, None), (None, "http"))
        second = Backend("ollama", RuntimeError(CANARY), (other, None))
        w = FallbackInterpreter(first, second, valid)
        w.interpret("a", None)
        self.assertIs(w.interpret("b", None), GOOD)
        self.assertEqual(meta(w) | {"last_seconds": None}, {"last_error": None, "last_backend": "openai",
                         "last_fallback": False, "last_primary_error": None, "last_seconds": None})
        self.assertIs(w.interpret("c", None), other)
        self.assertEqual((w.last_error, w.last_backend, w.last_fallback, w.last_primary_error),
                         (None, "ollama", True, "http"))
        self.assertEqual((len(first.calls), len(second.calls)), (3, 2))

    def test_final_normal_failure_and_invalid_object_stay_unchanged(self):
        w = FallbackInterpreter(Backend("openai", (None, "timeout")),
                                Backend("ollama", ({"unsupported": FAILED}, "timeout")), valid)
        self.assertEqual(w.interpret("a", None), {"unsupported": FAILED})
        self.assertEqual((w.last_error, w.last_primary_error), ("timeout", "timeout"))
        odd = ["not", "a", "reply"]
        checked = []

        def broken(result):
            checked.append(result)
            raise RuntimeError(CANARY)

        w = FallbackInterpreter(Backend("openai", (GOOD, None)), Backend("ollama", (odd, "contract-ish")), broken)
        self.assertIs(w.interpret("b", None), odd)
        self.assertEqual((w.last_error, w.last_primary_error, w.last_fallback), ("contract-ish", "contract", True))
        self.assertEqual(checked, [GOOD])

    def test_final_context_forwarding_and_no_error_leak(self):
        pending, notes, aliases, recent = {"p": 1}, ["n"], {"a": "b"}, [("me", "x")]
        sent_at = object()
        first = Backend("openai", (None, "timeout"))
        second = Backend(None, RuntimeError(CANARY + " owner prompt"))
        w = FallbackInterpreter(first, second, valid)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = w.interpret("text", pending, notes, aliases, sent_at=sent_at, recent=recent)
        for b in (first, second):
            (args, kw), = b.calls
            self.assertEqual(args, ("text", pending, notes, aliases))
            self.assertTrue(all(x is y for x, y in zip(args[1:], (pending, notes, aliases))))
            self.assertIs(kw["sent_at"], sent_at)
            self.assertIs(kw["recent"], recent)
        self.assertEqual((pending, notes, aliases, recent), ({"p": 1}, ["n"], {"a": "b"}, [("me", "x")]))
        self.assertIsNone(w.last_backend)
        self.assertNotIn(CANARY, out.getvalue() + err.getvalue() + json.dumps(result) + json.dumps(meta(w)))
        first, second = Backend("openai", (None, "timeout")), Backend("ollama", KeyboardInterrupt())
        w = FallbackInterpreter(first, second, valid)
        with self.assertRaises(KeyboardInterrupt):
            w.interpret("text", None)
        self.assertEqual((len(first.calls), len(second.calls)), (1, 1))


if __name__ == "__main__":
    unittest.main()
