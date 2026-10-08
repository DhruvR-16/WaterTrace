# ChartCourt

**Read between the axes.** An evidence-led visual audit for chart screenshots, built for the OpenCV AI Competition 2026.

ChartCourt measures bars, reads axis ticks, highlights the evidence, and reconstructs supported charts with a zero baseline and conventional axis direction. In the included truncated-axis example, the visible bars suggest a 4× ratio, while the recovered values differ by approximately 6.5%.

**Current implementation:** local Python / OpenCV 5 app. It detects nonzero baselines and inverted axes in single-series, solid-color vertical bar charts with readable linear numeric axes. An uncertain scale triggers a second, targeted OCR pass; unresolved images are referred for review. No AI API key is needed. The policy agent is a bounded state machine, not an LLM.

## Quick start

Prerequisites: Python 3.13, Git, and the Tesseract executable. On macOS, install Tesseract with `brew install tesseract`; on Debian/Ubuntu, use `sudo apt-get install tesseract-ocr`. No API keys, cloud account, or hardware are needed to run locally.

```sh
git clone https://github.com/DhruvR-16/opencv_hackathon.git
cd opencv_hackathon
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [ChartCourt locally](http://127.0.0.1:8000). Upload, drag-and-drop, or paste a PNG/JPEG/WebP up to 8 MB and 20 megapixels. Images must be at least 100 pixels wide and tall. Examples are included and are inspected through the same pipeline as uploads. Stop the server with `Ctrl+C`.

On Windows, use `py -3.13 -m venv .venv` and replace `.venv/bin/python` with `.venv\Scripts\python.exe`; Tesseract must be installed and available on `PATH`. The documented verification was performed on macOS, not Windows.

## What works

- Four real image examples: truncated axis, conventional axis, inverted axis, and missing ticks.
- Color segmentation, contour geometry, OCR tick reading, linear axis calibration, and value estimation.
- Targeted reinspection when the axis is ambiguous, with recorded metrics and decision thresholds.
- Original/reconstruction comparison, evidence overlays, recovered values table, inspection trace.
- Downloadable reconstructed SVG, estimates CSV, and JSON inspection report with the original file's SHA-256 digest.
- Upload validation, bounded OCR execution and inspection concurrency, no persistent upload storage.
- Responsive browser workspace and keyboard-accessible controls.

## Data flow

```text
Image bytes → decode/resize → OpenCV colored-bar contours → axis crop OCR
  → fit scale → if unclear: enlarge + CLAHE + OCR → fit again
  → unresolved: review / resolved: recover bar values → axis findings → reconstruct
```

`app/vision.py` only sees image bytes and a display filename. It does not read fixture names, labels, expected answers, or sample metadata. The backend returns measured evidence and the browser renders it.

## Verification

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate.py
```

Tests run real OCR. They cover numerical recovery, changed filenames, a resized JPEG, erased axes causing reinspection/refusal, blank images, malformed uploads, upload size limits, and sample routing. The initial local suite has **16 passing tests**; see [VERIFICATION.md](VERIFICATION.md) for checks and outstanding validation. These are fixture tests, not an accuracy claim on real-world charts.

Regenerate our self-authored examples with `.venv/bin/python scripts/generate_samples.py`. Numerical ground truth lives in `tests/fixtures/truth.json` and is never served to the inspection pipeline. Development dependencies include Matplotlib only for fixture generation.

## Current boundaries

- Intended for positive, single-series vertical bars with visible solid colors and a linear axis. Stacked/grouped bars, negative bars, log/broken axes, monochrome charts, pictograms, and infographic layouts are unsupported. Detection heuristics can still misinterpret unsupported inputs; results need inspection.
- Three consistent OCR ticks are required. A good fit is an internal consistency check, not a calibrated probability of correctness.
- Values are estimates from pixel positions. Decimal precision is reported for inspection, not a promise of equivalent source-data accuracy. OCR category names can be wrong.
- Truncated/inverted axes are design choices to investigate. They do not establish malicious intent, and a clean axis does not establish truthful source data.
- The app reads available evidence; it does not retrieve or verify the original dataset or accompanying claims.
- The local app makes no claim of AWS deployment, COOL execution, public benchmark accuracy, or award eligibility. The application does not retain uploads after processing; the multipart framework may temporarily spool large uploads to disk during a request. Downloaded reports remain on the user's device. Google Fonts is requested for typography and has local font fallbacks.

## Hackathon deployment

AWS deployment remains required for the competition and is not yet performed. The repository includes a container recipe:

```sh
docker build -t chartcourt .
docker run --rm -p 127.0.0.1:8000:8000 chartcourt
```

The image includes standard OpenCV 5, not COOL. It can be hosted on an appropriate AWS compute service. A public deployment needs HTTPS, access control and request/body limits at the proxy; this initial server binds to loopback for local use.

For the COOL award, use the official compatible Graviton Marketplace environment, preserve its OpenCV installation, install the other dependencies, run this same workload there, and measure against standard OpenCV 5 on equivalent hardware. Do not install `requirements.txt` over the COOL environment: that would replace its OpenCV package. Record the actual imported library path/build info. `cool_verified` is deliberately false until such verification exists.

## Evaluation roadmap

Use licensed subsets of [PlotQA](https://github.com/NiteshMethani/PlotQA) (CC BY 4.0) and [Misviz](https://tudatalib.ulb.tu-darmstadt.de/items/21f65047-c4d8-45a2-a717-e76f63dd0c33) (CC BY-SA 4.0). Neither dataset has been downloaded or evaluated in this version. Preserve attribution and license requirements. Filter to supported vertical-bar layouts using a fixed published protocol; separate tuning from held-out tests by source/data family, including paired variants. Report coverage/refusal rate alongside issue precision/recall and numeric error. Include clean charts and unsupported charts to expose false accusations and mistaken reconstructions.

## API

- `GET /api/health`: runtime OpenCV version, OCR availability and deployment label.
- `GET /api/samples`: public example titles, without numerical truth.
- `POST /api/samples/{id}/analyze`: inspect an allowlisted example image.
- `POST /api/analyze`: multipart field `file`; returns findings, geometry, ticks, trace, image preview and reconstructed SVG when supported.
- `/docs`: generated API reference.

Example upload from a second terminal while the server is running:

```sh
curl --fail http://127.0.0.1:8000/api/analyze \
  -F 'file=@app/static/samples/truncated.png'
```

The JSON response contains findings, the input file's SHA-256 digest, evidence boxes, recovered estimates, actual inspection steps, and a reconstruction when the evidence supports it.

## Repository layout

```text
app/
  main.py              FastAPI routes, upload validation, concurrency limits
  vision.py            OpenCV geometry, OCR, axis policy, reconstruction
  static/              Browser interface and self-authored example PNGs
scripts/
  generate_samples.py  Reproducible example chart generation
  evaluate.py          Evaluation against fixture ground truth
tests/
  fixtures/truth.json  Ground truth; never used by the analysis pipeline
  test_inspection.py   Real-OCR regression and API tests
```

## Privacy and repository hygiene

The local application does not send chart images to an external AI service or retain uploads after processing. Large multipart uploads can use temporary disk storage during a request. Google Fonts is the only intentional external browser request, for typography; system-font fallbacks are included.

Do not commit real user uploads, confidential reports, cloud credentials, or `.env` files. Local environments, keys, datasets, artifacts, and common credential files are excluded from Git; the Docker build context is restricted to runtime files. These exclusions do not replace reviewing staged changes or scanning Git history. See [SECURITY.md](SECURITY.md) for deployment boundaries and safe secret handling.

## Next milestones

The initial deliverable is a runnable MVP. Next competition milestones: independent dataset evaluation, improved support detection, user feedback, real AWS deployment and measured COOL execution, then report/video preparation.
