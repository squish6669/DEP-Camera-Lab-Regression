# DEP Camera Lab Regression

Regression test bench for the DEP Universal Drive Camera Lab.

The active development and release corpus is now treated as **one unified 123-image batch**. The original 68-image set remains useful only as historical regression evidence; it is no longer a separate operational batch and should not be used as the primary development denominator.

## What the workflow does

`Camera Lab Unified Corpus Regression` expands `Camera Roll.zip`, verifies that the image count and ground-truth row count match, verifies that every image filename has one corresponding ground-truth record, and requires the complete **123-image corpus** before OCR scoring begins.

The workflow checks out the current `squish6669/RapidOCRCSharp` source, builds the Windows x64 RapidOCR benchmark, runs PP-OCRv5 across the complete corpus, and scores output against `data/Camera-Lab-Ground-Truth.csv`.

The report tracks serial recognition, model recognition, capacity extraction, OCR errors, runtime, manufacturer-level accuracy, and every remaining miss. Ground-truth fields should cover manufacturer, exact model, serial, capacity, drive type, and CT/tracking when those values are visually verifiable.

## Corpus policy

- Active denominator: **123 images**.
- Treat all images as one Camera Lab corpus, not separate batches.
- New drive images extend the same corpus rather than creating a new numbered batch.
- The original 68-image results are retained only as a no-regression checkpoint.
- No ground-truth value should be guessed. Unreadable fields remain blank/unverified.
- Serial behavior must not regress while model and capacity extraction are improved.

## Regression gate

`regression-thresholds.json` protects the proven recognition baseline. The unified workflow also fails before OCR if the image archive is incomplete, the ground-truth row count does not match the image count, or image/ground-truth filenames do not match.

## Development loop

1. Maintain the full 123-image corpus and its verified ground truth.
2. Patch model/capacity/serial extraction logic or RapidOCR integration.
3. Push the patch.
4. GitHub runs the entire 123-image corpus automatically.
5. Review regression summary, capacity summary, CSV, and JSON artifacts.
6. Repeat until accuracy and safety targets are reached.

The County workstation is reserved for final real-camera/WPF verification instead of being required for every development iteration.
