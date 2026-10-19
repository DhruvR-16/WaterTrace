# Local operations evidence and deployment gates

## Measured local CLI smoke benchmark — 19 October 2026

Three sequential, separate process launches of the same 512×512 India demo.
Includes interpreter startup, file decoding, pipeline, preview generation and
report export. The filesystem cache was not flushed; these are **not three cold
disk runs**, a load test, a p95 estimate or AWS measurements.

Environment: Darwin 25.6.0 arm64; Python 3.13.6; OpenCV 5.0.0;
NumPy 2.2.6; Rasterio 1.5.2. Input SHA-256:
`d720e440668b59affe70047b8e3694d04917abe10309c0a342ecdb000f14319f`.

| Run | Wall time (seconds) | Maximum resident set size (bytes, macOS time) |
|---|---:|---:|
| 1 | 0.64 | 128385024 |
| 2 | 0.62 | 128237568 |
| 3 | 0.29 | 128434176 |

Reproduce on macOS, choosing a new output filename on each run:

```sh
/usr/bin/time -l .venv/bin/python -m watertrace.cli \
  data/watertrace/data/flood_events/HandLabeled/S1Hand/India_285297_S1Hand.tif \
  --date 2016-08-12 --output artifacts/new-timing-run.json
```

Other operating systems use different `time` options and RSS units. Do not compare
numbers without recording the platform, workload, cache state and measurement
boundary. This small input does not establish the peak memory for maximum-sized
paired uploads or concurrent analysis.

## Current behavior

- Malformed or unsupported raster: validation error, no accepted result; run
  `scripts/smoke_watertrace.py` against a running localhost service to check
  malformed-input recovery and a subsequent successful analysis.
- Capacity: native analysis slots are bounded at two; extra work can receive
  HTTP 429. Browser cancellation stops waiting, not necessarily native work.
- Restart: browser notes are not server-persisted. Export review JSON before
  leaving; restore only onto matching inputs. A restart is not a backup strategy.
- Inputs: uploads are transient, but native raster parsers are not sandboxed.
  Trusted files only. Locations/notes in exports may be sensitive.
- Access: localhost host/origin bounds, no multi-user authentication. Do not
  expose the app with a public tunnel or wildcard trusted-host setting.
- Container: bounded Compose configuration exists and validates; execution is
  unverified while the Docker daemon is unavailable.

## AWS completion gates — not yet fulfilled

Account/profile, region and total spending cap must be provided before creating
resources. No credentials should enter chat, Git, images or reports. Then:

1. Agree on authenticated access and upload isolation; preserve trusted-input
   scope unless native parsing has appropriate isolation.
2. Build and exercise the container, including maximum-size and concurrent loads.
3. Deploy the actual analysis pipeline, not merely the dashboard assets.
4. Record image digest, commit, environment, request provenance, measured memory,
   latency and failure/restart behavior from the actual cloud runtime.
5. Verify log redaction and retention; document infrastructure and network costs.
6. Tear down the owned resources and verify that dependent billable resources
   have also been removed. Budget alerts alone are not a hard spending limit.

No AWS use, cost estimate, public endpoint, production readiness or cloud
performance is claimed by the local benchmark. See the submission pack for the
remaining video, access and competition requirements.
