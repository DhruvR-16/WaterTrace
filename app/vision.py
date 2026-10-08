"""Image-only, bounded chart inspection. No fixture metadata enters this pipeline."""
from __future__ import annotations

import base64
import hashlib
from html import escape
from io import BytesIO
import re
import time

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract

MAX_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    pass


def decode_image(raw: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(raw)) as im:
            if im.width * im.height > MAX_PIXELS:
                raise InvalidImage("Image is too large. Use an image under 20 megapixels.")
            if im.format not in {"PNG", "JPEG", "WEBP"}:
                raise InvalidImage("Choose a PNG, JPEG, or WebP chart image.")
            im = ImageOps.exif_transpose(im)
            rgba = im.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            im = background.convert("RGB")
            im.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            rgb = np.array(im)
        if min(rgb.shape[:2]) < 100:
            raise InvalidImage("This image is too small. Use a chart at least 100 pixels wide and tall.")
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("Could not read this image. Choose a PNG, JPEG, or WebP under 20 megapixels.") from exc


def image_url(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise InvalidImage("Could not encode the inspection image.")
    return "data:image/png;base64," + base64.b64encode(encoded).decode()


def number(text: str) -> float | None:
    token = text.strip().replace("−", "-").replace("–", "-").replace(",", "")
    token = re.sub(r"^[€£$]", "", token).rstrip("%")
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", token):
        return None
    value = float(token)
    return value if abs(value) < 1e12 else None


def ocr(image: np.ndarray, *, offset=(0, 0), scale=1, psm=11) -> list[dict]:
    if not image.size:
        return []
    data = pytesseract.image_to_data(image, config=f"--psm {psm}",
                                   output_type=pytesseract.Output.DICT, timeout=15)
    words = []
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not text.strip() or conf < 25:
            continue
        x, y, w, h = (int(data[k][i]) / scale for k in ("left", "top", "width", "height"))
        words.append(dict(text=text.strip(), confidence=round(conf / 100, 3),
                          box=[round(x + offset[0]), round(y + offset[1]), round(w), round(h)]))
    return words


def find_bars(image: np.ndarray) -> tuple[list[dict], str]:
    """Find solid, colored, separate rectangles sharing an endpoint."""
    h, w = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 60, 45]), np.array([179, 255, 255]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        fill = cv2.contourArea(contour) / (bw * bh)
        if (.014 * w < bw < .24 * w and .022 * h < bh < .82 * h
                and bw * bh > .001 * h * w and fill > .87
                and .06 * h < y and y + bh < .95 * h):
            color = image[y + bh // 2, x + bw // 2]
            candidates.append(dict(box=[x, y, bw, bh], color="#%02x%02x%02x" % tuple(int(c) for c in color[::-1])))
    if len(candidates) < 2:
        return [], "bottom"
    best, edge = [], "bottom"
    tolerance = max(4, h * .008)
    for side in ("bottom", "top"):
        for anchor in candidates:
            ax, ay, aw, ah = anchor["box"]
            base = ay + ah if side == "bottom" else ay
            group = [c for c in candidates if abs((c["box"][1] + (c["box"][3] if side == "bottom" else 0)) - base) <= tolerance]
            if len(group) > len(best):
                best, edge = group, side
    best.sort(key=lambda c: c["box"][0])
    # Exclude stacked or overlapping marks: the MVP supports one series only.
    if len(best) < 2 or len(best) > 24 or any(a["box"][0] + a["box"][2] > b["box"][0] for a, b in zip(best, best[1:])):
        return [], edge
    widths = np.array([c["box"][2] for c in best])
    if np.max(widths) / np.min(widths) > 1.8:
        return [], edge
    return best, edge


def axis_ticks(words: list[dict], image_width: int) -> list[dict]:
    numeric = []
    for word in words:
        value = number(word["text"])
        if value is not None:
            numeric.append({**word, "value": value, "cy": word["box"][1] + word["box"][3] / 2})
    if len(numeric) < 3:
        return []
    # Tick labels are right-aligned; their right edges form a column.
    groups = []
    for anchor in numeric:
        right = anchor["box"][0] + anchor["box"][2]
        group = [t for t in numeric if abs(t["box"][0] + t["box"][2] - right) < max(12, image_width * .018)]
        if len(group) >= 3:
            groups.append(group)
    if not groups:
        return []
    ticks = max(groups, key=lambda g: (len(g), np.mean([t["box"][0] for t in g])))
    ticks.sort(key=lambda t: t["cy"])
    unique = []
    for tick in ticks:
        if not unique or abs(tick["cy"] - unique[-1]["cy"]) > 8:
            unique.append(tick)
    return unique


def fit_axis(ticks: list[dict]) -> tuple[float, float, float] | None:
    if len(ticks) < 3:
        return None
    ys = np.array([t["cy"] for t in ticks])
    values = np.array([t["value"] for t in ticks])
    span = float(np.ptp(values))
    if span < 1e-9 or np.ptp(ys) < 30:
        return None
    a, b = np.polyfit(ys, values, 1)
    residual = float(np.max(np.abs(a * ys + b - values)) / span)
    return float(a), float(b), residual


def reconstruction_svg(bars: list[dict], unit: str) -> str:
    W, H, left, right, top, bottom = 800, 480, 85, 765, 70, 402
    maximum = max(b["value"] for b in bars)
    ymax = max(1, maximum * 1.12)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" aria-label="Reconstructed chart with a zero baseline">',
             '<rect width="800" height="480" fill="#fff"/>',
             '<text x="85" y="35" font-family="Arial,sans-serif" font-size="18" font-weight="600" fill="#263643">Reconstructed from visible evidence</text>']
    for tick in np.linspace(0, ymax, 5):
        y = bottom - tick / ymax * (bottom - top)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#e6e9ea"/>')
        parts.append(f'<text x="70" y="{y+5:.2f}" text-anchor="end" font-family="Arial,sans-serif" font-size="14" fill="#687583">{tick:.1f}</text>')
    step = (right - left) / len(bars)
    for i, bar in enumerate(bars):
        height = bar["value"] / ymax * (bottom - top)
        x = left + i * step + step * .22
        parts.extend([
            f'<rect x="{x:.2f}" y="{bottom-height:.2f}" width="{step*.56:.2f}" height="{height:.2f}" rx="3" fill="{bar["color"]}"/>',
            f'<text x="{left+(i+.5)*step:.2f}" y="{bottom-height-10:.2f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" font-weight="600" fill="#263643">≈ {bar["value"]:.1f}{escape(unit)}</text>',
            f'<text x="{left+(i+.5)*step:.2f}" y="428" text-anchor="middle" font-family="Arial,sans-serif" font-size="14" fill="#687583">{escape(bar["label"][:22])}</text>',
        ])
    parts.append('<text x="85" y="465" font-family="Arial,sans-serif" font-size="12" fill="#87919a">Values are estimated from pixels. The underlying source data has not been verified.</text></svg>')
    return "".join(parts)


def analyze(raw: bytes, filename: str = "chart.png") -> dict:
    started = time.perf_counter()
    image = decode_image(raw)
    h, w = image.shape[:2]
    traces: list[dict] = []
    findings: list[dict] = []
    overlays: list[dict] = []

    def trace(tool, action, detail, metrics=None):
        elapsed = round((time.perf_counter() - started) * 1000)
        previous = traces[-1]["elapsed_ms"] if traces else 0
        traces.append(dict(step=len(traces) + 1, tool=tool, action=action, detail=detail,
                           metrics=metrics or {}, elapsed_ms=elapsed, duration_ms=elapsed - previous))

    def result(status, summary, bars=None, axis=None, svg=None, comparison=None):
        return dict(status=status, summary=summary, filename=filename[:160], image=image_url(image),
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    width=w, height=h, bars=bars or [], axis=axis, findings=findings, overlays=overlays,
                    trace=traces, reconstruction=svg, comparison=comparison,
                    processing_ms=round((time.perf_counter() - started) * 1000),
                    engine=dict(opencv=cv2.__version__, ocr="Tesseract", policy="axis-audit-v1",
                                deployment="local", cool_verified=False),
                    scope="Single-series, solid-color vertical bar charts with a readable linear numeric axis. Design checks do not verify the truth of the source data.")

    trace("decode_image", "Inspect image", f"Decoded a {w} × {h} image. Analysis uses pixels only.", {"width": w, "height": h})
    bars, edge = find_bars(image)
    trace("detect_bar_geometry", "Locate chart marks", f"Found {len(bars)} aligned solid bars using color masks and contours.",
          {"bars_found": len(bars), "shared_edge": edge})
    if len(bars) < 2:
        findings.append(dict(kind="unsupported", severity="review", title="Chart structure needs review",
                             detail="Could not isolate at least two solid vertical bars. Try a single-series bar chart with visible axes.", evidence=[]))
        trace("inspection_policy", "Stop reconstruction", "Insufficient bar geometry. No numeric values or repair will be invented.")
        return result("review", "This image needs a closer look.")
    for i, bar in enumerate(bars):
        overlays.append(dict(box=bar["box"], label=f"Bar {i+1}", kind="bar"))

    xmin = min(b["box"][0] for b in bars)
    y0, y1 = int(h * .10), int(h * .90)
    x1 = max(1, xmin - 6)
    crop = image[y0:y1, :x1]
    try:
        words = ocr(crop, offset=(0, y0))
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        trace("read_axis", "OCR unavailable", str(exc)[:180])
        findings.append(dict(kind="ocr_unavailable", severity="review", title="Axis reader unavailable", detail="Tesseract is missing or exceeded its time limit. The image has not been assessed.", evidence=[]))
        return result("review", "Axis reading could not complete.")
    ticks = axis_ticks(words, w)
    fit = fit_axis(ticks)
    trace("read_axis", "Read numeric ticks", f"Read {len(ticks)} aligned axis ticks.",
          {"ticks": [t["value"] for t in ticks], "fit_error": round(fit[2], 4) if fit else None})

    # Actual perception-decision-action loop: weak or inconsistent OCR changes the tool call.
    if fit is None or fit[2] > .025:
        trace("inspection_policy", "Reinspect axis crop", "Fewer than 3 usable ticks or axis-fit error above 2.5%; switch to enlarged grayscale OCR.",
              {"minimum_ticks": 3, "max_fit_error": .025})
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        enlarged = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(enlarged)
        try:
            retry_words = ocr(enhanced, offset=(0, y0), scale=2, psm=6)
            retry_ticks = axis_ticks(retry_words, w)
            retry_fit = fit_axis(retry_ticks)
            if retry_fit and (not fit or retry_fit[2] < fit[2] or (retry_fit[2] <= .025 and len(retry_ticks) > len(ticks))):
                ticks, fit = retry_ticks, retry_fit
        except RuntimeError:
            trace("read_axis_detail", "OCR time limit", "The additional crop inspection did not complete within the time limit.")
        trace("read_axis_detail", "Resolve axis evidence", f"Axis now has {len(ticks)} usable ticks.", {"ticks": [t["value"] for t in ticks]})
    if fit is None or fit[2] > .025:
        findings.append(dict(kind="unreadable_axis", severity="review", title="A reliable scale is missing",
                             detail="At least three consistent numeric ticks are required. A missing, nonlinear, or unreadable axis prevents reconstruction.", evidence=ticks))
        trace("inspection_policy", "Request human review", "Axis scale remains ambiguous after targeted reinspection. Reconstruction is withheld.")
        return result("review", "There is not enough evidence to reconstruct this chart.")

    a, b, error = fit
    slope_values = np.diff([t["value"] for t in ticks])
    if not (np.all(slope_values > 0) or np.all(slope_values < 0)):
        trace("inspection_policy", "Request human review", "Tick values are not monotonic. Axis interpretation is ambiguous.")
        return result("review", "The axis scale could not be verified.")
    for tick in ticks:
        overlays.append(dict(box=tick["box"], label=tick["text"], kind="tick"))
    bases = [bar["box"][1] + (bar["box"][3] if edge == "bottom" else 0) for bar in bars]
    baseline_px = float(np.median(bases))
    baseline = float(a * baseline_px + b)
    span = abs(ticks[-1]["value"] - ticks[0]["value"])
    tolerance = max(span * .018, abs(a) * 3)
    if abs(baseline) <= tolerance:
        baseline = 0.0
    axis = dict(slope=a, intercept=b, baseline=round(baseline, 3), inverted=a > 0,
                fit_error=round(error, 5), ticks=ticks, tolerance=round(tolerance, 4),
                range=[min(t["value"] for t in ticks), max(t["value"] for t in ticks)])
    trace("calibrate_axis", "Map pixels to values", f"Linear tick fit error: {error*100:.2f}% of the axis range. Visible bar baseline: {baseline:.2f}.",
          {"baseline": axis["baseline"], "inverted": a > 0, "fit_error": error})

    for i, bar in enumerate(bars):
        x, y, bw, bh = bar["box"]
        endpoint = y if edge == "bottom" else y + bh
        bar["value"] = round(float(a * endpoint + b), 2)
        bar["pixel_length"] = bh
        bar["label"] = f"Bar {i+1}"
    # Read category labels independently; failure does not fabricate names.
    label_y = min(h - 1, int(max(max(t["cy"] for t in ticks), max(bar["box"][1] + bar["box"][3] for bar in bars)) + 8))
    try:
        label_crop = cv2.resize(image[label_y:], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        label_words = ocr(label_crop, offset=(0, label_y), scale=2, psm=6)
        for bar in bars:
            x, y, bw, bh = bar["box"]
            center = x + bw / 2
            candidates = [word for word in label_words if abs(word["box"][0] + word["box"][2] / 2 - center) < bw * .85]
            if candidates:
                top = min(word["box"][1] for word in candidates)
                row = sorted([word for word in candidates if abs(word["box"][1] - top) < 16], key=lambda v: v["box"][0])
                bar["label"] = " ".join(word["text"] for word in row)[:50]
    except RuntimeError:
        pass
    trace("recover_values", "Measure bar endpoints", "Applied the fitted scale to each bar endpoint; category names come from OCR when readable.",
          {"estimated_values": [bar["value"] for bar in bars]})
    # Restrict reconstruction to observed endpoints inside the calibration envelope.
    low, high = axis["range"]
    if baseline < -tolerance or any(bar["value"] < -tolerance or bar["value"] < low - tolerance or bar["value"] > high + tolerance for bar in bars):
        findings.append(dict(kind="unresolved_geometry", severity="review", title="Bar geometry and scale disagree",
                             detail="Some endpoints fall outside the calibrated positive scale. This layout needs manual interpretation.", evidence=[]))
        trace("inspection_policy", "Request human review", "Recovered endpoints violate the calibrated range; no corrected chart is generated.")
        return result("review", "The measurements need human review.", axis=axis)
    for bar in bars:
        bar["value"] = max(0, bar["value"])

    if baseline > tolerance:
        findings.append(dict(kind="truncated_axis", severity="warning", title="The bars start above zero",
                             detail=f"The visible baseline is approximately {baseline:.1f}. Bar lengths therefore amplify proportional differences. A zero-baseline comparison makes that effect visible.",
                             evidence=[ticks[-1]] if a < 0 else [ticks[0]]))
    if a > 0:
        findings.append(dict(kind="inverted_axis", severity="warning", title="The numeric axis runs downward",
                             detail="Larger values appear lower in the image. This reverses the usual visual direction; context determines whether the choice is appropriate.", evidence=[ticks[0], ticks[-1]]))
    if not findings:
        findings.append(dict(kind="axis_checks_passed", severity="pass", title="The axis checks pass",
                             detail="The detected bars share a zero baseline and the values increase upward. This does not establish that the source data or wider claim is true.", evidence=[]))

    comparison = None
    if baseline > tolerance and not axis["inverted"]:
        smallest, largest = min(bars, key=lambda x: x["value"]), max(bars, key=lambda x: x["value"])
        if smallest["value"] > 0 and smallest["pixel_length"] > 0:
            apparent = largest["pixel_length"] / smallest["pixel_length"]
            actual = largest["value"] / smallest["value"]
            comparison = dict(apparent_ratio=round(apparent, 2), value_ratio=round(actual, 3),
                              actual_change_pct=round((actual - 1) * 100, 2),
                              first_label=smallest["label"], second_label=largest["label"],
                              explanation="Ratio of the longest to shortest visible bar, compared with the ratio of their recovered numeric values.")
    trace("inspection_policy", "Reconstruct chart", "Scale and bar geometry agree. Rebuild from recovered values with zero baseline and conventional upward direction.",
          {"findings": [f["kind"] for f in findings]})
    unit = "%" if any("%" in t["text"] for t in ticks) else ""
    svg = reconstruction_svg(bars, unit)
    trace("verify_reconstruction", "Check preserved values", "The output uses the same recovered values; only the baseline and axis direction change.",
          {"bar_count": len(bars), "data_source": "pixel_estimates"})
    status = "flagged" if any(f["severity"] == "warning" for f in findings) else "clear"
    summary = "The presentation changes the apparent comparison." if status == "flagged" else "No supported axis issue found."
    return result(status, summary, bars, axis, svg, comparison)
