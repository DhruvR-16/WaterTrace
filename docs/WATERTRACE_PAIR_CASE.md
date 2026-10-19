# Beira: real paired observations, not validated flood change

## Reproduce locally

This is a separate historical case, not a new built-in example or an extension of the Sen1Floods11 accuracy benchmark. It needs internet access for public catalog/COG reads, but no account, AWS credentials or paid API. It does not deploy anything on AWS.

```sh
# First inspect the metadata-only plan; no raster is downloaded.
.venv/bin/python scripts/prepare_watertrace_pair.py
# Explicitly approve acquisition and processing of the bounded public crop.
.venv/bin/python scripts/prepare_watertrace_pair.py --approve-download
```

The default new directory is `data/watertrace-pairs/beira-2019/`, ignored by Git. Existing directories are never overwritten. To rerun, choose a different `--output` path. Files are private on POSIX. A publication failure may leave completed files in the new directory; retain them for diagnosis and use a fresh destination. Nothing is recursively deleted.

Verify the prepared case offline before a demonstration:

```sh
.venv/bin/python scripts/prepare_watertrace_pair.py --verify
```

This checks both local crop sizes/SHA-256 against the manifest, then reproduces the saved report with the installed engine. Only generation timestamp and runtime duration are excluded from the comparison; evidence, dates, policies, zones and measurements must agree. It makes no network calls, downloads or file changes. Exit `0` means reproduced, `1` means a crop/report mismatch or missing crop, and `2` means malformed/unreadable inputs or a replay error. `--verify` and `--approve-download` cannot be combined. Symlink inputs, duplicate manifest keys, oversized JSON and invalid fingerprints are rejected. A mismatch after an engine/library update may be a reproducibility change rather than corruption; preserve the original files and investigate, never silently regenerate the manifest. This verifies local consistency, not the authenticity of the manifest or the correctness of original acquisition metadata.

Upload `current.tif` dated **2019-03-26**, with `earlier.tif` dated **2019-03-02**. Consult `provenance.json` before confirming matching acquisitions. Select **Paired change evidence** or **Radar · VV → Compare radar dates**. The wipe uses identical grids and a fixed backscatter scale, without a misleading current-water overlay on the earlier image. The queue always describes current observations.

## Provenance and selection

- Digital Earth Africa `s1_rtc`, tile S20E034, Sentinel-1A, relative orbit 6, descending, IW, VV/VH.
- Earlier STAC ID: `331dfc45-6f48-5ae3-be69-9d5c075f7e49`.
- Current STAC ID: `9188a45d-a054-50d5-bd8f-c0f334cf0860`.
- EPSG:4326, 0.0002-degree grid; fixed window column 3500 / row 3500 / width 512 / height 512. Bounds approximately 34.7–34.8024°E, 19.8024–19.7°S. This is a coastal study window, not verified cropland.
- Provider values are linear gamma0 power. Conversion uses `10*log10` of finite positive values; only mask value 1 is retained. Masked pixels, NoData and provider shadow-invalid pixels remain invalid. Header/grid checks precede conversion; normal upload validation then runs on the result.
- The explicit baseline cutoff is March 9. Copernicus documented flooding before the cyclone's landfall, so March 14 would not be a defensible assumed dry baseline. March 2 is **earlier**, not independently confirmed dry.
- The planner checks metadata and shortlists; it neither validates ground conditions nor autonomously acquires data. Wrong platform/orbit/grid, missing fields, mixed assets, unsupported units and incomplete catalog pages stop or exclude candidates. Search and local arrays are bounded; COG block transfer volume depends on the remote file layout.

Sources: [provider specifications, quality mask and access terms](https://docs.digitalearthafrica.org/en/latest/data_specs/Sentinel-1_specs.html), [pre-cyclone flood report](https://mapping.emergency.copernicus.eu/news/copernicus-ems-monitors-major-flood-in-mozambique/), [Cyclone Idai mapping activation context](https://mapping.emergency.copernicus.eu/news/copernicus-ems-monitors-major-tropical-cyclone-in-mozambique/).

Attribution: Contains modified Copernicus Sentinel data (2019), processed by Digital Earth Africa / Sinergise. Raw imagery and derived raster files are not committed. Recheck source terms and attribution before distributing demo media. Provider calibration differs from the original benchmark inputs; do not transfer accuracy figures between them.

## Observed local pipeline result — 19 October 2026

| Measurement | Result |
|---|---:|
| Study-window area | 12,166.259 ha |
| Current water-like evidence | 2,987.694 ha |
| Current uncertain/unobserved | 989.598 ha |
| Current assessed fraction | 91.87% |
| Assessable at both dates | 82.36% |
| Current water without an assessable earlier baseline | 812.755 ha |

These are classifier outputs, **not measured flooded hectares**. No independently date-matched flood labels were scored. Unknown earlier water is neither new nor repeated water; repeated water does not prove continuous flooding. Dates are 24 days apart and may miss the peak event.

Local output SHA-256:

- Current: `56c2822ba4675a5b689713a5593723256f5ab72550de5e80e43c58e4646bc74b`.
- Earlier: `6b416c6fb5afbc67d1bd7cfcbf6d485138a2fd62640fa23a1530d4963d88603f`.

Hashes identify this encoded local run, not signed upstream authenticity. Encoding/library changes may alter GeoTIFF bytes. The generated manifest retains source metadata, URLs, window, conversion and local digests for inspection.

## Still missing

Independent temporal truth with compatible dates and valid-area masks; agricultural boundaries; field review; a validated cross-provider detector. Copernicus event reports establish context but are not substitute ground truth. This case demonstrates ingestion, pairing, masking, provenance and abstention—not detection superiority.
