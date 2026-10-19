# Data provenance and reproducibility

## Public research data

The downloader reads the public [Sen1Floods11 v1.1](https://github.com/cloudtostreet/Sen1Floods11) bucket at `https://storage.googleapis.com/sen1floods11/v1.1/`. See the upstream [dataset documentation](https://github.com/cloudtostreet/Sen1Floods11/blob/master/docs/README.md).

Attribution: Bonafilia, Tellman, Anderson & Issenberg (2020), Cloud to Street, *Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1*. Contains modified Copernicus Sentinel data.

The project does not redistribute dataset rasters in Git or Docker. Public download access is not proof of redistribution permission. We did not find an authoritative standalone upstream license file during this build; mirror license labels were not treated as permission. Confirm upstream terms before distributing rasters, derived previews, public demos or competition media. The code's license cannot relicense third-party data.

## Selection and separation

Demo selection is deterministic: the first Spain, India and USA rows in the dataset's training split CSV. They were not selected using held-out test performance.

| Example | Chip | Radar date | Optical date | Relative orbit |
|---|---|---|---|---:|
| Eastern Spain | Spain_5923267 | 2019-09-17 | 2019-09-18 | 110 |
| Northeast India | India_285297 | 2016-08-12 | 2016-08-12 | 77 |
| Central United States | USA_994009 | 2019-05-22 | 2019-05-22 | 136 |

Dates and orbit context come from the upstream event metadata. The default zones are synthetic survey subdivisions, not agricultural ground truth. No real farmer identity or ownership record is included. Normal analysis reads `S1Hand` for classification and `S2Hand` only for optical display. The separate Evidence Lab reads `LabelHand` only after inference, for evaluation overlays and scoring; labels cannot change classifications, summaries or review decisions.

The benchmark reads all 90 pairs from `splits/flood_handlabeled/flood_test_data.csv`. Labels are used only for scoring. The classifier does not take a filename, country, label or expected outcome as input.

The Evidence Lab deliberately selects four cases from that already exposed test split: `India_80221` (highest India chip IoU, a stronger contrast), `India_44475` (false positives with no labeled water), `Pakistan_167553` (weak overlap) and `Sri-Lanka_534068` (severe missed water). This post-hoc selection is not representative validation. See [case dates, scores and limitations](WATERTRACE_SHOWCASE.md). Real lab exports carry radar and reference-label SHA-256 digests plus attribution. Synthetic exercises are generated from code, not real satellite observations or geographically validated farms.

## Local files

`scripts/fetch_watertrace_data.py --split demo|lab|valid|test` downloads explicit subsets, caps each object at 32 MiB, and writes a manifest of object paths, sizes and SHA-256 hashes. It checks all existing split manifests for conflicting records and altered cached files before downloading. Recorded files are reused only when their sizes and hashes match. Unrecorded files require a byte-hash match against a fresh download; differing contents are preserved and rejected, not silently overwritten or re-recorded. Missing recorded files can be restored only from matching downloaded bytes. New manifests also include the selection CSV; older manifests remain readable and verify only their listed objects.

Run `python scripts/verify_watertrace_data.py --split demo` offline, with optional `--data /absolute/cache/path`, to verify listed files without changing them. Exit `0` means all listed objects match, `1` means an object is missing/changed/unreadable, and `2` means the manifest cannot be used. JSON output identifies affected relative paths. Manifests are limited to 4 MiB and 10000 objects, paths cannot traverse or use symlink components, and duplicate or malformed records are rejected. This is local consistency checking, not cryptographic endorsement by the dataset authors or proof that a split is complete. It cannot detect coordinated changes to both data and its local manifest, and it does not validate raster semantics.

On mismatch, retain the manifest, inspect or move the identified file aside, then rerun the appropriate downloader. Conflicting manifests require manual reconciliation; they are never automatically chosen or rewritten to hide disagreement. Download publication uses exclusive hard links, and manifests are staged/flushed before replacement. Interrupted batches can retain successfully downloaded objects, but do not publish an incomplete new manifest. Hard-link support is required; hostile concurrent filesystem mutation and power-loss durability are outside this trusted-local-cache contract.

Downloads and generated reports stay under ignored `data/` and `artifacts/`. Reviewers should retain the manifest alongside evaluation outputs. A report identifies its radar bytes by SHA-256 and records coordinates/dates; it is not an authenticated acquisition certificate.

## Temporal observations

The included data only provide single snapshots for each demo. A matching 2019-05-10 / 2019-05-22 Sentinel-1A, ascending orbit 136 pair was found in the [Planetary Computer RTC catalog](https://planetarycomputer.microsoft.com/dataset/sentinel-1-rtc), but that collection's access documentation requires an account for data-read tokens. No account was created, no access restriction was bypassed, and no pair download or real temporal validation is claimed. The upload comparison is implemented and tested with synthetic paired rasters; acquire a licensed matched real pair and ground context before presenting it as field-validated.

Do not mix provider calibrations, pass directions or polarization conventions just because two rasters cover the same coordinates. Terrain-corrected products can have different grids. Reprojection alone does not make acquisitions radiometrically comparable.
