#!/usr/bin/env python3
"""Build deterministic OCR-only label-region views for diagnostic rereads.

This helper intentionally consumes only physical images plus OCR detection geometry.
It never reads ground truth and does not infer or rewrite serial/model/capacity values.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}
INT_RE = re.compile(r"-?\d+")


def parse_box(value: str):
    nums = [int(x) for x in INT_RE.findall(value or "")]
    if len(nums) < 8:
        return None
    xs = nums[0::2][:4]
    ys = nums[1::2][:4]
    return min(xs), min(ys), max(xs), max(ys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--detections", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--expected-count", type=int, required=True)
    args = ap.parse_args()

    image_root = Path(args.images)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(
        [p for p in image_root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
        key=lambda p: p.name.lower(),
    )
    if len(images) != args.expected_count:
        raise SystemExit(f"Expected {args.expected_count} source images; found {len(images)}")
    lowered = [p.name.lower() for p in images]
    if len(set(lowered)) != len(lowered):
        raise SystemExit("Duplicate source image filenames are not allowed")

    boxes = defaultdict(list)
    with open(args.detections, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("FileName") or "").strip()
            if not name:
                continue
            try:
                box_conf = float(row.get("BoxConfidence") or 0)
            except ValueError:
                box_conf = 0.0
            # Geometry is useful even when recognition text is blank. Keep only
            # reasonably confident detections so spurious page-edge boxes do not
            # expand the crop unpredictably.
            if box_conf < 0.55:
                continue
            box = parse_box(row.get("Coordinates") or "")
            if box:
                boxes[name.lower()].append(box)

    map_rows = []
    for src in images:
        with Image.open(src) as opened:
            im = ImageOps.exif_transpose(opened).convert("RGB")

        detected = boxes.get(src.name.lower(), [])
        if detected:
            x0 = min(b[0] for b in detected)
            y0 = min(b[1] for b in detected)
            x1 = max(b[2] for b in detected)
            y1 = max(b[3] for b in detected)
            bw = max(1, x1 - x0)
            bh = max(1, y1 - y0)
            # A modest deterministic margin retains nearby model/capacity text
            # without turning the view back into a full-frame reread.
            mx = max(24, round(bw * 0.08))
            my = max(24, round(bh * 0.12))
            x0 = max(0, x0 - mx)
            y0 = max(0, y0 - my)
            x1 = min(im.width, x1 + mx)
            y1 = min(im.height, y1 + my)
            view = im.crop((x0, y0, x1, y1))
            source = "ocr-detection-union"
        else:
            view = im.copy()
            x0, y0, x1, y1 = 0, 0, im.width, im.height
            source = "full-frame-fallback"

        # Deterministic, conservative enhancement: grayscale autocontrast retains
        # literal label evidence while increasing local legibility for the reread.
        view = ImageOps.grayscale(view)
        view = ImageOps.autocontrast(view, cutoff=0.5)
        view = ImageEnhance.Contrast(view).enhance(1.15)
        view = view.filter(ImageFilter.UnsharpMask(radius=1.2, percent=125, threshold=3))
        view = view.convert("RGB")

        out_name = f"{src.stem}__label.jpg"
        out_path = out_dir / out_name
        view.save(out_path, "JPEG", quality=95, subsampling=0)
        map_rows.append(
            {
                "SourceFile": src.name,
                "ViewFile": out_name,
                "Method": source,
                "X0": x0,
                "Y0": y0,
                "X1": x1,
                "Y1": y1,
            }
        )

    if len(map_rows) != args.expected_count:
        raise SystemExit(f"Expected {args.expected_count} label views; built {len(map_rows)}")

    map_path = out_dir / "Label-Region-Map.csv"
    with map_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(map_rows[0].keys()))
        writer.writeheader()
        writer.writerows(map_rows)

    print(f"Built {len(map_rows)} deterministic label-region views at {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
