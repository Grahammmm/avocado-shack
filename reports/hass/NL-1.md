# HASS-NL-1: natural-language interpreter, before and after tables

Two measured tables from the HASS-NL-1 natural-language eval. Both were scored by
`hass/nl_eval.py` at scorer commit `e0fdda6`. Neither table says anything about any
other case, model or machine.

## Table A: Qwen3.6 35b, 43 cases (historical)

Historical result, kept verbatim from the HASS-NL-1 receipt `report_qwen.md`. Scored at
`e0fdda6` on a shared CPU, so the latency rows depend on what else was running.

| Measure | before | after |
|---|---|---|
| Cases scored | 43 | 43 |
| Intent accuracy | 60.5% | 81.4% |
| Strict accuracy (right ops, args, words) | 53.5% | 79.1% |
| Wrong-draft rate (unsafe) | 18.6% | 4.7% |
| Drafted where a draft was NOT right | 25.0% | 0.0% |
| Asked a question when it should ask | 42.9% | 85.7% |
| Refused when it should refuse | 27.3% | 90.9% |
| Over-cautious (asked or refused a clear request) | 33.3% | 22.2% |
| JSON valid | 100.0% | 97.7% |
| Calls failed at the end | 0 | 1 |
| First attempts that timed out | 0 | 5 |
| Latency p50 (s) | 64.0 | 25.0 |
| Latency p95 (s) | 85.8 | 104.0 |

## Table B: Gemma4 12b, 22 cases

Produced by the scorer at `e0fdda6`:

```
python3 hass/nl_eval.py report --run before=<base_gemma.jsonl> --run after=<after_gemma.jsonl>
```

`before` is `base_gemma.jsonl` (what the service sent before HASS-NL-1). `after` is
`after_gemma.jsonl` (with the HASS-NL-1 prompt rules).

| Measure | before | after |
|---|---|---|
| Cases scored | 22 | 22 |
| Intent accuracy | 36.4% | 59.1% |
| Strict accuracy (right ops, args, words) | 31.8% | 54.5% |
| Wrong-draft rate (unsafe) | 4.5% | 0.0% |
| Drafted where a draft was NOT right | 0.0% | 0.0% |
| Asked a question when it should ask | 60.0% | 60.0% |
| Refused when it should refuse | 50.0% | 100.0% |
| Over-cautious (asked or refused a clear request) | 88.9% | 88.9% |
| JSON valid | 86.4% | 100.0% |
| Calls failed at the end | 3 | 0 |
| First attempts that timed out | 16 | 22 |
| Latency p50 (s) | 82.5 | n/a |
| Latency p95 (s) | 118.2 | n/a |

### Compare result

```
python3 hass/nl_eval.py compare --before <base_gemma.jsonl> --after <after_gemma.jsonl>
{"compared": 22, "fixed": ["n072", "n178", "n198", "n207", "n257", "n271"], "newWrongDrafts": [], "regressed": [{"id": "n237", "why": "unsupported where question was right"}], "stillWrongDrafts": []}
```

Compared 22 cases: 6 fixed, 1 regressed (n237), `newWrongDrafts` empty. The command
exits 1 whenever any case regressed, so exit 1 is expected here.

### Read this before using Table B

- **After-run latency is n/a and must not be compared.** In the after run every first
  attempt timed out at 120 s and succeeded only on the 900 s retry, because the local CPU
  was contended by another card's benchmark. The after-run latency says nothing about the
  model, and the before-run latency (p50 82.5 s, p95 118.2 s) must not be set against it.
- **The before run had 3 calls fail at the end** (still `timeout` after the retry). They
  are in the 22 scored cases, so they count against the before figures.
- **The before run's first attempts also timed out often** (16 of 22, per the table).
  Treat its latency row with caution; no cause for the before-run timeouts is claimed
  beyond what the receipts show.
- **22 cases only.** The accuracy figures describe these 22 cases and nothing wider. The
  size of the improvement is not an estimate for other cases. One case regressed (n237).
  Table A is a different model on a different case set (43) and is not comparable to Table B.
- Machine-valid scorer output; review required, not semantic acceptance.
