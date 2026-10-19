# WaterTrace

**Satellite evidence. Grounded decisions.** A local satellite-image workspace for reviewing possible surface-water exposure and deciding where human inspection needs more evidence.

WaterTrace helps reviewers trace satellite water evidence across observations, without implying an automated flood warning or verified crop-damage diagnosis.

Repository: [DhruvR-16/WaterTrace](https://github.com/DhruvR-16/WaterTrace).

Built for a proposed farming-cooperative / NGO post-flood workflow: **water observations and missing evidence go into separate review queues.** A missing observation must not look like a safe field. No sensors, API keys, cloud account, or AI subscription are needed for the local examples.

**Status: working research prototype, not a validated agricultural decision system.** It uses actual Sentinel-1 imagery and OpenCV 5, not a simulated satellite dashboard. It does not establish crop damage, flood depth, continuous flooding, soil waterlogging, or access safety. We have not demonstrated superiority to operational flood-mapping systems.

## Run locally

### Upgrading from earlier names

Version 0.9 adopts the final name **WaterTrace** (previously Inundra / FieldWatch). Use the commands below, `WATERTRACE_DATA` / `WATERTRACE_DEPLOYMENT` instead of the former `INUNDRA_*` or `FIELDWATCH_*` variables, and `data/watertrace/` for the default cache. Existing clones should update their origin to `https://github.com/DhruvR-16/WaterTrace.git`. Stop any old running server and restart with `watertrace.main:app`.

For other checkouts, move the existing `data/inundra/` or `data/fieldwatch/` cache to `data/watertrace/` only if the destination does not already exist, or set `WATERTRACE_DATA` to the old cache's absolute path. Do not merge or overwrite datasets. This workspace's cache has already been moved without changing its contents. The local checkout folder name need not match the repository name; leaving it in place preserves virtual-environment paths.

New geographic exports use the `watertrace` metadata member and `geojson-review-v3` schema (previously `inundra` / `geojson-review-v2`, originally `fieldwatch` / `geojson-review-v1`). Consumers must update that metadata lookup; geometry, measurements and classification policies are unchanged. The benchmark's method key is likewise now `watertrace`, with unchanged counts and source hashes. Matching v0.7 and v0.8 full review JSON files can still restore notes because branding is not part of the analysis-context comparison; earlier incompatible policy/zone contexts remain rejected. Existing exports and Git history are not rewritten, and legacy temporary-file patterns remain ignored for safety.

### Setup

Python 3.13 is the tested version. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_watertrace_data.py --split demo
.venv/bin/python -m uvicorn watertrace.main:app --host 127.0.0.1 --port 8000
```

Open [the local workspace](http://127.0.0.1:8000). Stop with `Ctrl+C`. The download is about 11 MB and is saved under ignored `data/watertrace/`. After downloading, these examples and all analysis run offline. For Windows, substitute `.venv\Scripts\python.exe`; Windows has not been verified.

Without downloading, upload your own **trusted, north-up, calibrated VV/VH dB GeoTIFF**. Exactly two bands (VV, VH), at most 24 MiB and 2 million pixels, at least 16×16, with a CRS and local extent. Calibration and terrain correction happen upstream; the app cannot verify them from pixel values alone.

## What you can do

- Compare matching acquisitions with a keyboard-accessible radar wipe and a categorical change view that keeps missing earlier evidence distinct from new water. Reproduce the [Beira public-data pair](docs/WATERTRACE_PAIR_CASE.md) locally; it is a pipeline case, not validated flood-change accuracy.
- Start with India, then replay actual historical observations from Spain and the USA. Optical imagery is context only, not an inference input or cloud-screened truth.
- Open **Evidence Lab** for four selected real contrast cases from India, Pakistan and Sri Lanka, plus nine executable synthetic hard cases. Inspect reference labels and false-alarm/missed-water maps without feeding labels to inference.
- Inspect field-level review gates: insufficient resolution/coverage, rice/paddy context, missing earlier baselines, repeat observations, water candidates and low signal. These gates do not certify safe or damaged fields.
- Inspect OpenCV-derived water evidence, uncertain pixels, and geographic review zones.
- Draw zones on EPSG:4326 imagery, or import longitude/latitude GeoJSON for any supported raster CRS. Polygons are user-provided, not inferred farm boundaries.
- Compare an earlier/current pair on the exact same CRS, grid, and dimensions after confirming matching orbit, direction, polarization, and calibration. Report new-water candidates, water seen at both dates, and current water without a usable earlier baseline separately. **Two dates never imply continuous duration.**
- Filter water/uncertainty queues, select zones on the image or list, add human review notes, and export a JSON evidence report with source digests, geometry, policy, dates, and trace.
- Export all review boundaries as GeoJSON for a geographic handoff, retaining measured water/unknown areas, review gates, provenance and separate unverified notes. These polygons are **review zones, not detected water outlines**.
- Run the same pipeline through a local CLI. Original imagery is excluded from CLI/report exports; coordinates and notes may still be sensitive.

Reviews exist only in the current page memory. Draft notes are captured when selecting another zone or exporting. Switching observations or reanalyzing zones warns before replacing unexported notes; cancel to export first. If the request fails, times out or is cancelled, the previous accepted observation, original inputs, selection, queue filter and notes are restored and labeled **PREVIOUS RESULT**. The failed request has not produced a new result. Resubmit the attempted inputs to retry, or export the restored review.

A successful replacement clears the previous notes, including a completed Evidence Lab rejection exercise (which shows no map or export). During a pending request, the old map is hidden and exports are disabled; unexported notes still trigger a browser-dependent leave warning. Recovery is only within this page session, not after reload/close or a browser crash, so **always verify your downloaded export before leaving**. No notes are automatically written to browser storage or sent to the server.

To resume: load the same radar inputs, dates, acquisition confirmation and zones, then choose **Restore notes** and select the exported JSON (up to 2 MiB). Restoration requires matching source/reference metadata, policy and zone details. Mismatched, duplicate or invalid notes are rejected without changing the current review. Only human annotations are restored—not measurements, classification, images or an authenticated identity. Custom polygons must be supplied again using the same GeoJSON.

Version 0.7 adds paired-evidence accounting and `review-gates-v3`, following the boundary-coverage metadata added in 0.5. Older review files will not automatically restore onto these changed reports; retain them and manually reconcile their notes. The original files are not modified or deleted.

The default 3×3 sectors are demonstration survey areas, not farms or a cropland mask. Included examples are single observations; real temporal-pair validation remains outstanding.

Zone inputs are limited to 200 KB, 100 polygons and 200 coordinates per polygon. Use unique JSON object keys, finite numeric values and nesting no deeper than 32 levels. Raw GeoJSON/CLI files must be UTF-8; legitimate multilingual names and emoji are supported. Invalid Unicode, ambiguous duplicate keys and oversized coordinate values are rejected with a validation error, not a report. Only validated polygon coordinates are retained from geometry objects; unrelated embedded geometry metadata is not copied into exports.

### Choose the right export

| Control | Purpose | What it does not do |
|---|---|---|
| **Export review** | Image-free evidence JSON and human notes; use **Restore notes** with matching original inputs | Does not authenticate human reports or save the original imagery |
| **Zones GeoJSON** | All geographic review zones, regardless of queue filter, with measurements and current draft notes | Not a water mask, crop-loss assessment, or restorable notes backup |

GeoJSON coordinates are longitude/latitude even for projected source rasters. Full review boundaries are retained, but all area measurements describe **pixel-center overlap with the image**, which can be smaller than the boundary. Overlapping zones must not be summed as unique affected land. Without an earlier observation, change measurements remain `null`, not zero. Source digests/dates, method policies, uncertainty and synthetic/selected-replay disclosures travel with the file. Human annotations do not change any measurement or review gate.

**Boundary coverage is not pixel quality.** The selected-zone panel labels boundaries as partial or within the image; uncertainty describes only the overlap. Reports and GeoJSON expose a separate `scene_clipped` flag and `scene_overlap_fraction` (a planar polygon-area ratio in the raster grid, not a geodesic hectare estimate or accuracy score). Any edge outside a tiny coordinate-roundoff tolerance withholds a whole-zone conclusion—even if less than 1% is missing or the rounded fraction reads `1`. Outside-image land is not counted as dry, wet, or assessed.

**Zero new-water candidates does not mean no new flooding.** A current water pixel with an unknown earlier state cannot be called either new or repeated water. Paired reports now show that missing-baseline area separately and distinguish current-image coverage from the area assessable at both dates. The `baseline_required` gate asks for earlier evidence; coverage/resolution and paddy-context gates still take precedence and retain the baseline warning. Completeness uses an unrounded boolean, so a tiny gap cannot disappear through display rounding. Without a pair, temporal support is `null`; with no current water, its water-baseline fraction/completeness are `null`, not an assurance of safety. These are evidence-accounting rules, not a new accuracy claim.

GeoJSON export deliberately leaves the unexported-notes warning active; also save **Export review** if you need to restore notes. Original custom-zone files should be retained: exported rings are normalized to counterclockwise order and may not match the exact geometry ordering required by note restoration. Zone imports remain limited to 200 KB; a large annotated export can exceed that limit. GIS software may discard custom metadata, so keep the full review JSON alongside any geographic handoff. External GIS application compatibility and the new button's browser layout have not yet been verified.

## Regional hard-case showcase

The scope is selected historical observations, not nationwide or worldwide monitoring. The Evidence Lab's nine synthetic exercises work without downloads. To enable its four real replays, download about 6.8 MB of radar, labels and metadata:

```sh
.venv/bin/python scripts/fetch_watertrace_data.py --split lab
.venv/bin/python scripts/check_watertrace_lab.py
```

Open **Evidence Lab** in the top bar. Test missing earlier pixels, repeated water, paddy context, four-pixel fields, a field just outside the image, conflicting radar, shifted grids and all-NoData inputs. A rejection produces no map, queue or export. Synthetic success demonstrates software contracts, not flood-detection accuracy. Read the [showcase guide and selection disclosure](docs/WATERTRACE_SHOWCASE.md).

## Evidence, not a headline accuracy score

The [filtered-baseline experiment](docs/WATERTRACE_EXPERIMENTS.md) adds two fixed controls without changing production inference. The [submission pack](docs/WATERTRACE_SUBMISSION.md) includes a report index, architecture diagram, recording script, reviewer protocol and local deployment rehearsal. AWS remains deferred by the owner; a completed submission is not claimed.

The initial fixed policy was evaluated on all **90 chips in the Sen1Floods11 v1.1 test split**, across 10 events and 20,517,367 labeled pixels. Inference never reads labels. One rejected scene remains in scoring as wholly unknown; unknown water counts as missed water, not as an excluded hard case.

| Method | Water precision | Water recall | Water IoU | Assessed labeled pixels |
|---|---:|---:|---:|---:|
| WaterTrace v1 | 75.6% | 52.9% | 45.1% | 68.6% |
| Single-band VH Otsu baseline | 25.5% | 72.2% | 23.2% | 99.6% |

**Interpretation:** fewer false positives and better pooled overlap than this simple baseline, but substantially more missed water. Performance varies sharply by event; WaterTrace's IoU is worse than the baseline in Pakistan and Sri Lanka. These are pixel-level water labels, **not evidence of crop-loss accuracy, time saved, or successful field inspections**. The test split is not event-disjoint from the dataset's training scenes and is now exposed for future development. See [benchmark protocol and all event results](docs/WATERTRACE_BENCHMARK.md).

## Verify and reproduce

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_watertrace_lab.py
node --test tests/watertrace.test.cjs
.venv/bin/python scripts/fetch_watertrace_data.py --split test
.venv/bin/python scripts/verify_watertrace_data.py --split test
.venv/bin/python scripts/evaluate_watertrace.py --split test --output artifacts/my-evaluation.json
```

The test download is about 147 MB. The evaluator refuses to replace an existing output file. Unit tests use self-generated rasters and need no network. Node 22+ is only needed for optional frontend tests; there is no frontend build step.

### Check cached datasets offline

```sh
.venv/bin/python scripts/verify_watertrace_data.py --split demo
```

Choose `demo`, `lab`, `valid`, or `test`; use `--data /absolute/cache/path` for a custom location. The command makes no network requests or file changes. It checks each manifest-listed object's size and SHA-256, reports `ok`, `missing`, `mismatch`, or `unreadable_or_unsafe`, and exits `0` for a matching cache, `1` for failed objects, or `2` for a missing/invalid manifest. This verifies consistency with a local record—not upstream authenticity, valid radar calibration, complete dataset membership, or scientific accuracy.

The downloader now checks existing manifests before reuse and refuses to silently record changed bytes as a fresh baseline. Missing objects can be downloaded again but must match their recorded hashes. Files not covered by a manifest must match a fresh download before reuse. On a mismatch, preserve or move the named file aside, then rerun the relevant download; do not delete the manifest to bypass the warning. Conflicting manifests require manual reconciliation. Downloaded objects are published without overwriting another writer, and manifests are replaced only after a complete staged write. A failed batch can leave completed objects for the next run, but does not publish a partial new manifest.

CLI example (after downloading the demos):

```sh
mkdir -p artifacts
.venv/bin/python -m watertrace.cli \
  data/watertrace/data/flood_events/HandLabeled/S1Hand/India_285297_S1Hand.tif \
  --date 2016-08-12 --output artifacts/india-review.json
```

Use `--reference earlier.tif --reference-date YYYY-MM-DD --same-orbit` for a verified matching pair, and `--zones zones.geojson` for your own review polygons. Output is created with mode `0600` on POSIX. Reports are fully written and flushed to a private temporary file in the output directory, then published without replacing an existing path—including symlinks. A handled write/publication failure removes the temporary file and does not create a partial report. This requires filesystem hard-link support; unsupported filesystems return an output error. A process crash can leave a private `.watertrace-*.tmp` file, and power-loss durability is not guaranteed. Exit codes: `0` saved, `2` invalid/unreadable input or output error, `3` output already exists. A saved report is not a safety clearance.

To create a geographic handoff instead, add `--format geojson` and choose a new output path such as `--output artifacts/india-zones.geojson`. The default remains `--format json`. CLI exports contain no browser-session notes; use the browser export to include those annotations. Both formats omit raster/preview payloads, but coordinates and notes can still disclose sensitive information.

## Architecture and boundaries

```text
Trusted radar GeoTIFF(s) + dates + optional GeoJSON
  → bounded local FastAPI upload → Rasterio / PROJ validation
  → OpenCV median filter → bounded Otsu → VV/VH agreement
  → connected components + explicit unknown pixels
  → optional exact-grid earlier/current comparison
  → geodesic areas + separate human-review queues
  → browser overlays, reviewer notes, provenance JSON / geographic zone handoff

Independent label rasters → evaluator / explicit Evidence Lab scoring AFTER inference
                           (never classification or review-queue inputs)
```

See [technical design](docs/WATERTRACE_ARCHITECTURE.md), [security boundaries](SECURITY.md), and [competition / portfolio readiness](docs/WATERTRACE_READINESS.md).

The default Dockerfile packages WaterTrace without datasets or credentials. It is prepared for local testing; **a container build/run has not yet been verified because the local Docker daemon is unavailable**. No AWS resources have been created. No AWS, Graviton, or COOL performance claim is made.

```sh
docker build -t watertrace:local .
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data/watertrace:/data:ro" watertrace:local
```

## Data and attribution

Examples and evaluation use [Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11), Bonafilia, Tellman, Anderson & Issenberg (2020), Cloud to Street; contains modified Copernicus Sentinel data. Downloads are kept outside Git. The upstream repository's licensing/redistribution terms need confirmation before distributing its rasters or derived previews; public access alone is not a redistribution license. See [data provenance](docs/WATERTRACE_DATA.md). The repository's code license does not grant rights to third-party data.

This branch contains WaterTrace only. The previous ChartCourt project is recoverable from [`codex/chartcourt-v0.3`](https://github.com/DhruvR-16/WaterTrace/tree/codex/chartcourt-v0.3) and Git history; its app, samples, tests and documents are no longer included in `main`.
