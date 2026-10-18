# FieldWatch readiness — 18 October 2026

## Working local scope

- Actual public Sentinel-1 scenes, OpenCV 5 classification, uncertainty overlays and geographic area accounting.
- Browser example selection, water/uncertainty filtering, zone drawing/import, human notes and report export.
- Bounded single/pair GeoTIFF upload, dates and grid guards; same engine exposed by CLI.
- Deterministic policy, separate evaluator, source hashes, baseline and per-event error reporting.
- Synthetic unit/integration tests and Node model tests; no network needed for those tests.
- India-first library and Evidence Lab: four disclosed selected real replays, nine generated hard-case exercises, reference/error maps and explicit whole-field review gates. No geographic accuracy improvement is claimed.

The Sites local-preview guidance informed browser verification and responsive layout. This Python/raster application was not published through Sites.

## Local verification record

- Paired-evidence release (0.7): **199 Python tests and 61 JavaScript tests passed**. Fixed a reproduced missing-baseline ambiguity: current water could have zero new/repeated-water area without an explicit explanation. Tests cover all nine class-state pairs, area weighting, zone masks, mixed new/repeated/unknown baselines, unpaired/null semantics, tiny gaps rounded to zero, review-gate precedence, API reports, browser/Python export parity and note-restoration context. The Sites skill guided local detail/timeline labels; inert-DOM tests are not fresh visual QA under the existing browser restriction. The nine synthetic exercises pass; the 90-chip regression reproduces the recorded results exactly and the pixel classifier is unchanged. Real matched-pair validation remains outstanding; no detection-accuracy improvement is claimed.
- Failed-analysis recovery release: **176 Python tests and 53 JavaScript tests passed**. Event-wiring tests now cover rollback after server rejection, network failure, invalid responses and rendering failure; cancellation/timeout with late responses; pending leave warnings; imported-zone/example selection recovery; original uploaded-file references; earlier-image layer recovery; repeated failures; successful replacement; and synthetic rejection with no stale map/export. Restored reports retain the original source and notes and are explicitly labeled **PREVIOUS RESULT**. Empty-string zone IDs no longer suppress draft capture. The Sites skill guided the local recovery flow; these inert-DOM tests are not browser/layout QA under the existing access restriction. No classifier or accuracy change is claimed.
- Input/save hardening release: **176 Python tests and 39 JavaScript tests passed**. Reproduced and fixed server errors from escaped invalid Unicode, overflowing coordinates and deeply nested JSON. Shared web/CLI parsing rejects ambiguous duplicate keys and non-finite metadata while preserving Hindi and emoji. Tests verify rejection followed by a successful request, no CLI output for invalid input, no arbitrary geometry-metadata passthrough, private complete-file publication, cleanup after storage/encoding errors, existing/dangling symlink protection and two competing writers. A live local HTTP smoke test passed raster decoding, malformed-input rejection/recovery, multilingual metadata and host bounds; the owned test server was stopped afterward. All nine synthetic exercises passed and the 90-chip regression remained unchanged. Frontend note/export regression tests remain green; no UI or classifier changes were made in this release. Browser visual QA, hosted CI billing and unverified local Docker limits remain as described below.
- Boundary-coverage release: **138 Python tests and 39 JavaScript tests passed**. Fixed a reproduced bug where a zone with under 1% outside the image received no partial-coverage warning. Tests cover all four edges in geographic/projected rasters, exact scene boundaries, coordinate roundoff, mostly-outside zones, fractions rounding to one, fully covered but unassessable pixels, structured review-gate precedence, geographic exports and UI labels. Added the ninth synthetic lab case, `partial-zone`; all nine exercises pass, and the 90-chip regression remains unchanged. `review-gates-v2` intentionally changes report context; older notes require manual reconciliation, not silent restoration. The Sites skill guided local detail-panel labeling; event-wiring tests are not fresh visual QA under the existing browser restriction. No new detection-accuracy claim is made.
- GeoJSON handoff release: **115 Python tests and 35 JavaScript tests passed**. Coverage includes six actual-pipeline browser/Python parity cases, source-projected to geographic coordinates, missing comparison values, overlapping/clipped zones, geometry re-import with unchanged measurements, private/no-overwrite CLI output, and draft notes remaining protected after geographic export. Coordinate validation now rejects numeric-looking strings and booleans rather than retaining invalid geographic values after NumPy coercion. Exterior winding is normalized without changing boundary extent. All eight lab exercises passed; the 90-chip regression reproduced the recorded results exactly. The Sites skill guided the local export control only; no deployment was performed. UI event wiring is unit-tested with inert DOM doubles, not a fresh browser/layout sign-off under the existing access restriction. External GIS application compatibility is not yet verified. No classifier or benchmark-score change is claimed.
- Review-continuity patch: **94 Python tests and 29 JavaScript tests passed**. Model tests exercise draft-change detection, export/restoration round trips, reordered JSON keys, changed observation/date/reference/policy/geometry/crop/gates, invalid/duplicate/oversized notes and prototype-looking IDs. Event-wiring unit tests use inert DOM doubles to check zone switching, replacement cancellation, export, leave warnings and successful/failed restoration; they are not browser/layout QA. An actual pipeline result also passed export-to-restoration integration. No fresh browser sign-off is claimed under the existing browser access restriction. The Method dialog now correctly discloses post-inference Evidence Lab label use. This patch does not change pixel classification or claim a new accuracy result.
- Cleanup release: **94 Python tests and 10 JavaScript tests passed**, with a fresh Python 3.13 environment installed from the retained requirements files. All eight lab checks and the 90-chip regression passed. The lower test total reflects removal of predecessor-only tests, not lost FieldWatch coverage. The current browser recheck was blocked by the in-app browser access policy; browser observations below describe the earlier Evidence Lab verification, not a new visual sign-off for this patch.
- The active suite contains only FieldWatch tests; obsolete ChartCourt tests and fixtures were removed with its runtime. Regression coverage includes malformed origins, strict GeoJSON shape/ring validation, null-zone rejection, paddy whitespace, invalid longitude, NaN previews, optical-context failure recovery and drawn-ID collisions.
- Small positive reported areas display as `<0.1 ha`, not zero; raster labels scale with image dimensions.
- All eight executable synthetic lab exercises passed. The 90-chip regression reproduced all original case hashes/counts, event metrics and pooled scores exactly; this is regression evidence on exposed data, not new blind validation.
- Live HTTP smoke test passed against the local server: synthetic GeoTIFF decoding, water result, invalid-input rejection and untrusted-host rejection.
- Browser checks passed for real India GeoTIFF upload; custom polygon drawing and reanalysis; GeoJSON import with a rice-context warning; uncertainty filtering; saved review; downloaded JSON without images; synthetic paired upload; earlier-layer switching; and 96×64 image/overlay aspect-ratio preservation.
- Responsive check at 390×844 showed no horizontal overflow. Normal desktop browser rendering was inspected; no console errors/warnings were reported in the tested flows.
- Evidence Lab browser checks passed for India and Sri Lanka metrics, isolated reference/error layers, four-pixel and paddy gates, shifted-grid rejection after a real result (no stale map/metrics/export), image-free lab JSON with disclosures, return to ordinary India analysis, and mobile library/report layouts. No console warnings/errors were recorded in these flows.
- A **synthetic** paired-raster UI test confirms the comparison interface, not real flood-change accuracy. No equivalent real-pair validation has been completed.
- Direct dependency consistency check passed. The upstream Starlette/httpx test-client deprecation warning remains. This is not a dependency vulnerability audit. Runtime and development dependencies now use only `requirements.txt` and `requirements-dev.txt`; obsolete OCR/plotting dependencies were removed.

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
5. Open Evidence Lab: compare stronger India overlap with Sri Lanka's high precision but very low recall; switch to the error map. Run the tiny-field and shifted-grid exercises. Follow the [showcase guide](FIELDWATCH_SHOWCASE.md).
6. Finish with the real-pair, agricultural-context and AWS work still needed—not an unearned reliability claim.

## Environment limits

Local macOS/Python 3.13 verification is separate from hosted CI. The Docker daemon was unavailable during this build, so the changed container has not been executed locally. GitHub Actions had an account billing/spending execution restriction on prior runs; no billing settings were changed. A green local test run does not imply a green hosted build.
