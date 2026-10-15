# FieldWatch readiness — 15 October 2026

## Working local scope

- Actual public Sentinel-1 scenes, OpenCV 5 classification, uncertainty overlays and geographic area accounting.
- Browser example selection, water/uncertainty filtering, zone drawing/import, human notes and report export.
- Bounded single/pair GeoTIFF upload, dates and grid guards; same engine exposed by CLI.
- Deterministic policy, separate evaluator, source hashes, baseline and per-event error reporting.
- Synthetic unit/integration tests and Node model tests; no network needed for those tests.

The Sites local-preview guidance informed browser verification and responsive layout. This Python/raster application was not published through Sites.

## Local verification record

- Native Python suite passed, including the preserved ChartCourt regressions. FieldWatch-specific coverage includes raster/GeoJSON admission, explicit unknowns, pair metadata/alignment, geographic area accounting, rejected-scene benchmark scoring, upload limits, host/origin guards and private CLI exports.
- Seven FieldWatch frontend-model tests passed; the 19 preserved ChartCourt network tests also passed.
- Live HTTP smoke test passed against the local server: synthetic GeoTIFF decoding, water result, invalid-input rejection and untrusted-host rejection.
- Browser checks passed for real India GeoTIFF upload; custom polygon drawing and reanalysis; GeoJSON import with a rice-context warning; uncertainty filtering; saved review; downloaded JSON without images; synthetic paired upload; earlier-layer switching; and 96×64 image/overlay aspect-ratio preservation.
- Responsive check at 390×844 showed no horizontal overflow. Normal desktop browser rendering was inspected; no console errors/warnings were reported in the tested flows.
- A **synthetic** paired-raster UI test confirms the comparison interface, not real flood-change accuracy. No equivalent real-pair validation has been completed.
- Direct dependency consistency check passed. Upstream Starlette/httpx and legacy Matplotlib deprecation warnings remain. This is not a dependency vulnerability audit.

## Competition readiness is not complete

The project still targets [OpenCV AI Competition 2026](https://opencv26.devpost.com/), but a local prototype is not a completed submission. Recheck the official [rules](https://opencv26.devpost.com/rules) before submitting; this checklist does not override them.

- Substantive OpenCV 5 use: implemented locally.
- Meaningful AWS deployment/component: **deferred by the project owner**. No account usage, spending or resources provisioned.
- Public endpoint or arranged live demonstration: not prepared; local-only now.
- Technical report: architecture, dataset, fixed policy, benchmark, failure modes and reproducible instructions are documented. Final submission formatting remains.
- Demo video: not recorded. Keep within the competition's stated limit and explicitly label historical imagery, unknown regions and research status.
- COOL/Graviton evidence: absent. Do not claim backend activation or performance without a real qualifying run and comparison.
- Agentic category: not claimed. This is a deterministic review workflow, not evidence of qualifying autonomous visual reasoning.
- Data/media redistribution permissions and third-party attribution: confirm before public demo/submission.

## What remains before a credible field pilot

1. Secure a licensed matching earlier/current pair, verify orbit/calibration/grid, and validate change against independent temporal truth. No fabricated before-images.
2. Restrict review to verified agricultural polygons; add permanent-water, terrain-shadow and crop-context exclusions with provenance. Evaluate paddy fields separately.
3. Test against stronger flood-mapping baselines on whole unseen events, with event-level uncertainty. The exposed 90-chip test split is now a regression benchmark, not a future blind test.
4. Ask actual cooperative/NGO reviewers to compare the queue with their current workflow. Measure false alarms, missed affected zones, and review time. No impact statistics are currently claimed.
5. Add authenticated persistence, retention controls, resource isolation and deployment monitoring if moving beyond a local trusted-user prototype.

## Honest portfolio framing

Suggested wording after verifying the repository yourself:

> Built a local geospatial review application using OpenCV 5, FastAPI, Rasterio and PROJ; implemented bounded GeoTIFF ingestion, explicit abstention, geographic polygon accounting, paired-observation checks, provenance reports and a 90-chip independent-label benchmark.

Explain the precision/recall trade-off and failure cases in an interview. Do not claim farmers served, damage prevented, live monitoring, production readiness, SOTA performance, AWS deployment, or competition awards without evidence.

## Demo sequence

1. Load Northeast India; show actual radar versus optical context and source date.
2. Explain blue water evidence versus amber unknowns; select a zone with substantial uncertainty.
3. Filter the uncertainty queue, add a clearly labeled reviewer note, export the evidence JSON.
4. Draw/import a review zone and show how pixel accounting changes without pretending it is a verified farm.
5. Show the benchmark, including weaker recall and the Pakistan/Sri Lanka failures.
6. Finish with the real-pair, agricultural-context and AWS work still needed—not an unearned reliability claim.

## Environment limits

Local macOS/Python 3.13 verification is separate from hosted CI. The Docker daemon was unavailable during this build, so the changed container has not been executed locally. GitHub Actions had an account billing/spending execution restriction on prior runs; no billing settings were changed. A green local test run does not imply a green hosted build.
