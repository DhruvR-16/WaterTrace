# FieldWatch

**Evidence before action.** A local satellite-image workspace for reviewing possible surface-water exposure and deciding where human inspection needs more evidence.

Built for a proposed farming-cooperative / NGO post-flood workflow: **water observations and missing evidence go into separate review queues.** A missing observation must not look like a safe field. No sensors, API keys, cloud account, or AI subscription are needed for the local examples.

**Status: working research prototype, not a validated agricultural decision system.** It uses actual Sentinel-1 imagery and OpenCV 5, not a simulated satellite dashboard. It does not establish crop damage, flood depth, continuous flooding, soil waterlogging, or access safety. We have not demonstrated superiority to operational flood-mapping systems.

## Run locally

Python 3.13 is the tested version. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/fetch_fieldwatch_data.py --split demo
.venv/bin/python -m uvicorn fieldwatch.main:app --host 127.0.0.1 --port 8000
```

Open [the local workspace](http://127.0.0.1:8000). Stop with `Ctrl+C`. The download is about 11 MB and is saved under ignored `data/fieldwatch/`. After downloading, these examples and all analysis run offline. For Windows, substitute `.venv\Scripts\python.exe`; Windows has not been verified.

Without downloading, upload your own **trusted, north-up, calibrated VV/VH dB GeoTIFF**. Exactly two bands (VV, VH), at most 24 MiB and 2 million pixels, at least 16×16, with a CRS and local extent. Calibration and terrain correction happen upstream; the app cannot verify them from pixel values alone.

## What you can do

- Start with India, then replay actual historical observations from Spain and the USA. Optical imagery is context only, not an inference input or cloud-screened truth.
- Open **Evidence Lab** for four selected real contrast cases from India, Pakistan and Sri Lanka, plus eight executable synthetic hard cases. Inspect reference labels and false-alarm/missed-water maps without feeding labels to inference.
- Inspect field-level review gates: insufficient resolution/coverage, rice/paddy context, repeat observations, water candidates and low signal. These gates do not certify safe or damaged fields.
- Inspect OpenCV-derived water evidence, uncertain pixels, and geographic review zones.
- Draw zones on EPSG:4326 imagery, or import longitude/latitude GeoJSON for any supported raster CRS. Polygons are user-provided, not inferred farm boundaries.
- Compare an earlier/current pair on the exact same CRS, grid, and dimensions after confirming matching orbit, direction, polarization, and calibration. Report new-water candidates separately from water seen at both dates. **Two dates never imply continuous duration.**
- Filter water/uncertainty queues, select zones on the image or list, add human review notes, and export a JSON evidence report with source digests, geometry, policy, dates, and trace.
- Run the same pipeline through a local CLI. Original imagery is excluded from CLI/report exports; coordinates and notes may still be sensitive.

Reviews exist only in the current page memory. **Export before changing observations, reanalyzing zones, refreshing, or closing.** The default 3×3 sectors are demonstration survey areas, not farms or a cropland mask. Included examples are single observations; real temporal-pair validation remains outstanding.

## Regional hard-case showcase

The scope is selected historical observations, not nationwide or worldwide monitoring. The Evidence Lab's eight synthetic exercises work without downloads. To enable its four real replays, download about 6.8 MB of radar, labels and metadata:

```sh
.venv/bin/python scripts/fetch_fieldwatch_data.py --split lab
.venv/bin/python scripts/check_fieldwatch_lab.py
```

Open **Evidence Lab** in the top bar. Test missing earlier pixels, repeated water, paddy context, four-pixel fields, conflicting radar, shifted grids and all-NoData inputs. A rejection produces no map, queue or export. Synthetic success demonstrates software contracts, not flood-detection accuracy. Read the [showcase guide and selection disclosure](docs/FIELDWATCH_SHOWCASE.md).

## Evidence, not a headline accuracy score

The initial fixed policy was evaluated on all **90 chips in the Sen1Floods11 v1.1 test split**, across 10 events and 20,517,367 labeled pixels. Inference never reads labels. One rejected scene remains in scoring as wholly unknown; unknown water counts as missed water, not as an excluded hard case.

| Method | Water precision | Water recall | Water IoU | Assessed labeled pixels |
|---|---:|---:|---:|---:|
| FieldWatch v1 | 75.6% | 52.9% | 45.1% | 68.6% |
| Single-band VH Otsu baseline | 25.5% | 72.2% | 23.2% | 99.6% |

**Interpretation:** fewer false positives and better pooled overlap than this simple baseline, but substantially more missed water. Performance varies sharply by event; FieldWatch's IoU is worse than the baseline in Pakistan and Sri Lanka. These are pixel-level water labels, **not evidence of crop-loss accuracy, time saved, or successful field inspections**. The test split is not event-disjoint from the dataset's training scenes and is now exposed for future development. See [benchmark protocol and all event results](docs/FIELDWATCH_BENCHMARK.md).

## Verify and reproduce

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_fieldwatch_lab.py
node --test tests/fieldwatch.test.cjs
.venv/bin/python scripts/fetch_fieldwatch_data.py --split test
.venv/bin/python scripts/evaluate_fieldwatch.py --split test --output artifacts/my-evaluation.json
```

The test download is about 147 MB. The evaluator refuses to replace an existing output file. Unit tests use self-generated rasters and need no network. Node 22+ is only needed for optional frontend tests; there is no frontend build step.

CLI example (after downloading the demos):

```sh
mkdir -p artifacts
.venv/bin/python -m fieldwatch.cli \
  data/fieldwatch/data/flood_events/HandLabeled/S1Hand/India_285297_S1Hand.tif \
  --date 2016-08-12 --output artifacts/india-review.json
```

Use `--reference earlier.tif --reference-date YYYY-MM-DD --same-orbit` for a verified matching pair, and `--zones zones.geojson` for your own review polygons. Output is created with mode `0600` on POSIX. Exit codes: `0` saved, `2` invalid/unreadable input or output error, `3` output already exists. A saved report is not a safety clearance.

## Architecture and boundaries

```text
Trusted radar GeoTIFF(s) + dates + optional GeoJSON
  → bounded local FastAPI upload → Rasterio / PROJ validation
  → OpenCV median filter → bounded Otsu → VV/VH agreement
  → connected components + explicit unknown pixels
  → optional exact-grid earlier/current comparison
  → geodesic areas + separate human-review queues
  → browser overlays, reviewer notes, provenance JSON

Independent label rasters → evaluator / explicit Evidence Lab scoring AFTER inference
                           (never classification or review-queue inputs)
```

See [technical design](docs/FIELDWATCH_ARCHITECTURE.md), [security boundaries](SECURITY.md), and [competition / portfolio readiness](docs/FIELDWATCH_READINESS.md).

The default Dockerfile packages FieldWatch without datasets or credentials. It is prepared for local testing; **a container build/run has not yet been verified because the local Docker daemon is unavailable**. No AWS resources have been created. No AWS, Graviton, or COOL performance claim is made.

```sh
docker build -t fieldwatch:local .
docker run --rm --read-only --tmpfs /tmp:rw,nosuid,size=128m \
  --cap-drop ALL --security-opt no-new-privileges \
  -p 127.0.0.1:8000:8000 \
  -v "$PWD/data/fieldwatch:/data:ro" fieldwatch:local
```

## Data and attribution

Examples and evaluation use [Sen1Floods11](https://github.com/cloudtostreet/Sen1Floods11), Bonafilia, Tellman, Anderson & Issenberg (2020), Cloud to Street; contains modified Copernicus Sentinel data. Downloads are kept outside Git. The upstream repository's licensing/redistribution terms need confirmation before distributing its rasters or derived previews; public access alone is not a redistribution license. See [data provenance](docs/FIELDWATCH_DATA.md). The repository's code license does not grant rights to third-party data.

This branch contains FieldWatch only. The previous ChartCourt project is recoverable from [`codex/chartcourt-v0.3`](https://github.com/DhruvR-16/opencv_hackathon/tree/codex/chartcourt-v0.3) and Git history; its app, samples, tests and documents are no longer included in `main`.
