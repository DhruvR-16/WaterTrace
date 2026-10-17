# FieldWatch technical design

## Intended job

Help a cooperative or NGO reviewer separate (1) areas with water-like evidence, (2) areas with insufficient evidence, and (3) areas with no substantial detected open-water signal. This is a proposed workflow, not a demonstrated customer outcome. No automatic farmer alerts, insurance decisions, interventions, or field visits occur.

## Implementation map

| Component | Responsibility |
|---|---|
| `fieldwatch/engine.py` | Bounded GeoTIFF decoding, georeferencing, classification, pair alignment, polygon summaries |
| `fieldwatch/service.py` | Source hashes, dates, trace, PNG overlays and structured reports |
| `fieldwatch/decisions.py` | Versioned field-review gates; independent of frozen pixel classification |
| `fieldwatch/lab.py` | Allowlisted selected replays, post-inference reference scoring, synthetic contract exercises |
| `fieldwatch/main.py` / `limits.py` | Local API, multipart validation, admission and body limits, privacy-safe errors |
| `fieldwatch/catalog.py` | Three allowlisted historical examples and optical previews |
| `fieldwatch/static/` | Buildless UI, map/zone selection, drawing/import, in-memory human review and JSON export |
| `fieldwatch/cli.py` | Same analysis without a browser; private no-overwrite output |
| `scripts/evaluate_fieldwatch.py` | Separate independent-label scoring; never imported by inference |

## Fixed v1 image policy

1. Read exactly two north-up georeferenced VV/VH bands in dB. Reject unsupported formats, missing CRS, oversized extents and insufficient valid pixels. Plausible negative values do not prove correct calibration.
2. Preserve NoData, non-finite and out-of-range pixels. Fill invalid pixels with a median only for the filtering operation; erode the valid neighborhood so the fill never becomes assessed evidence.
3. Apply OpenCV 3×3 median filtering independently to each polarization.
4. Quantize a fixed −40 to +5 dB range and compute Otsu thresholds. Bound VV to [−22, −12] dB and VH to [−30, −20] dB.
5. Water-like: both filtered bands below their thresholds minus 1.5 dB. No-water signal: both above their thresholds plus 1.5 dB. All disagreement stays unknown.
6. OpenCV connected-components analysis removes water components under nine pixels **to unknown, not to dry**. Eight-neighbor connectivity is used.
7. If an earlier image exists, enforce exactly matching CRS, grid, dimensions, ordered dates, and user confirmation of acquisition compatibility. New-water candidates require earlier no-water / current water; earlier unknown does not qualify. Repeat-water means observed at both endpoints, not continuous inundation.

The heuristic is transparent and fast, but not a learned model or calibrated confidence score. OpenCV is substantive: median filtering, Otsu, valid-neighborhood erosion, connected components and visualization encoding execute in the actual inference path. The current distribution reports OpenCV 5.0.0. No COOL backend or Graviton run has been verified.

## Geographic accounting

PROJ converts geographic polygons to the input grid. Shapely validates simple exterior-only polygons, then clips to the scene. Rasterio uses pixel-center inclusion. Areas use WGS84 geodesic cell areas, calculated at each row's center and replicated across the short row; this is an approximation on projected grids. Overlapping review zones are not disjoint and must not be summed as unique affected land. Scene totals describe the whole image, not only imported zones.

Default zones are an explicitly illustrative 3×3 grid. Real field ownership, crop type and crop boundaries are not inferred. Under-25-pixel zones, over-30%-unknown zones, clipped zones and rice/paddy context receive caution reasons. Water at or above 5% of the overlap sends a zone to the water queue; otherwise uncertainty/context issues send it to uncertainty review. The 5% threshold is a workflow heuristic, not a proven agronomic threshold. High-water zones may still have substantial uncertainty; both values remain visible.

The additive `review-gates-v1` decision distinguishes a pixel measurement from a whole-field interpretation. Insufficient resolution/coverage takes precedence, followed by explicit rice/paddy context, repeated water without new candidates, water candidates and low signal. It always withholds crop-damage, water-depth, continuous-duration and access-safety claims. Engine reasons preserve an insufficient-coverage gate even if display rounding reaches 70%. This is a review policy, not a calibrated confidence model; the original water/uncertainty queue remains a signal index, not an actionable clearance.

## Contracts

- `GET /api/health`: readiness, OpenCV version, local/container label, no COOL claim.
- `GET /api/examples`: allowlisted examples and local availability.
- `POST /api/examples/{id}/analyze`: optional GeoJSON body; no arbitrary paths/URLs.
- `POST /api/analyze`: current TIFF; optional earlier TIFF; dates; same-orbit confirmation; optional GeoJSON.
- `GET /api/lab`: fixed cases and local availability. `POST /api/lab/{id}/run`: fixed inputs only, no body or client-supplied paths. Uses the same two-slot admission limit as analysis. Missing real data returns actionable 503; unknown IDs return 404.
- Lab reports add `lab` metadata and optional reference/error images after inference. Synthetic expected rejections return `kind: rejection_check` without images or summaries; the browser clears old results and disables export. Standard report export strips all preview images, retaining selection disclosures and reference provenance.
- JSON schema version `1.0`: source/reference, summary, zones, policy, trace, limitations and PNG previews. Exports omit previews. Human reviews are added only by the client and never overwrite algorithmic findings.

## Deliberate trade-offs

- No external map service: avoids keys and leaking user field coordinates. The image has selectable georeferenced overlays, not a global basemap. No geocoding, pan/zoom or live satellite ingestion is implemented.
- No LLM: outputs follow inspectable policies; this is not claimed as an autonomous agent.
- No database: local images are not intentionally retained; reviewer notes are temporary and must be exported. Drafts survive zone selection, and replacement/leave guards warn about unexported changes. A local JSON restoration flow validates an exact analysis-context match and restores only human notes. This is not automatic persistence or authenticated collaboration; both remain future work.
- No automatic reprojection: silent resampling could conceal bad temporal pairing. Upstream calibration/alignment are explicit responsibilities.
- No cloud deployment now: locally bounded requests are not equivalent to production access control, resource isolation or operational reliability.

## Known scientific gaps

Radar shadow, smooth dry soil and permanent water can mimic flood water; vegetation and urban scattering can hide water. No terrain-shadow exclusion, crop mask, vegetation exclusion, permanent-water baseline or crop-stage context is applied. The uncertainty class does not capture all errors. Test results measure water segmentation, not the queue's usefulness. A real matched temporal pair, event-disjoint comparison against stronger published baselines, and review by remote-sensing/agricultural practitioners are required before operational claims.
