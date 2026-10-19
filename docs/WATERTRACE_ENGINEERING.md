# Engineering case studies and interview evidence

This document describes repository behavior and measured limitations, not a claim
that a particular person independently authored every line. Be transparent about
AI assistance and demonstrate your own understanding of the decisions and tests.

## 1. An unknown baseline is not evidence of a dry field

**Problem:** current water with an unassessable earlier pixel must not be counted
as new flooding, repeated water, or earlier dry land. A zero new-water total can
otherwise look reassuring when the baseline is simply missing.

**Decision:** preserve three pixel states at both dates; account for all nine
combinations; export the area of current water without a usable baseline. Review
gates ask for evidence rather than forcing a binary answer. Continuous flooding
between two dates remains unknowable.

**Verification:** `tests/test_watertrace_temporal.py` and
`tests/test_watertrace_change.py`; replay the real Beira report with
`scripts/prepare_watertrace_pair.py --verify`. The replay verifies consistency,
not independently labeled temporal accuracy.

**Trade-off:** the system can return less decisive results. That is preferable
to inventing temporal support, but its practical value still needs evaluation.

## 2. A failed request must not destroy a review

**Problem:** switching observations can fail after a reviewer has entered notes.
Leaving old measurements under a new observation title misattributes evidence;
clearing everything loses useful work.

**Decision:** accept analysis as a transaction. Keep the prior accepted inputs,
report, selection and notes until replacement succeeds. On failure restore them
with an explicit previous-result label. Late responses after cancellation cannot
be accepted. Export remains necessary: drafts are not durable browser storage.

**Verification:** `tests/watertrace.test.cjs` covers rejected and cancelled
requests, late responses, selection/filter consistency, restoration and export.
These inert-DOM tests are not rendered-browser verification.

**Trade-off:** state management is more complicated than clearing the screen at
request start. Persistence and authenticated multi-user review are still absent.

## 3. A cache hash is not automatically trustworthy

**Problem:** hashing whatever file happens to exist can silently bless corrupted
cached data as a new baseline and make a later result appear reproducible.

**Decision:** compare existing bytes against the prior manifest, reject conflicting
manifests and unsafe paths, and require fresh source matching for unrecorded files.
Publish completed objects without overwriting another writer. Offline verification
never downloads, repairs, or rewrites the evidence it is checking.

**Verification:** `tests/test_watertrace_data_integrity.py` and
`tests/test_watertrace_pair_verification.py` cover corruption, incomplete transfers,
symlinks, manifest conflicts and changes between initial checking and replay.

**Trade-off:** integrity failures require deliberate reconciliation. A local hash
still does not prove upstream authenticity, calibration, or label correctness.

## Claims an interviewer can verify

- `make verify`: software tests, dependency consistency and synthetic hard cases.
- `make reproduce OUT=artifacts/interview-run`: exposed benchmark and uncertainty
  audit, using the existing verified test cache and a new output directory.
- `docs/WATERTRACE_BENCHMARK.md`: all-event results, including weaker Pakistan and
  Sri Lanka performance; not a selected best-case accuracy headline.
- `docs/WATERTRACE_UNCERTAINTY.md`: abstention's cost and limits, with event-cluster
  intervals rather than treating correlated pixels as independent trials.

Do not turn selective accuracy into “94.6% flood accuracy.” Unassessed regions and
missed water remain central limitations. Do not claim production deployment,
field impact, a blind evaluation, or independent authorship without evidence.

## Useful interview questions to answer yourself

Explain dB versus linear power; radar polarization agreement versus calibrated
confidence; spatial leakage between chips; pixel versus event uncertainty;
latitude-dependent pixel area; no-overwrite publication; and why a bounded upload
is not a native-parser sandbox. Point to a failing case before describing future
work. Describe a design you would change, including how you would test it.
