# DEP Camera Lab Regression

Private regression test bench for the DEP Universal Drive Camera Lab. The real 68-image drive-label corpus stays in this private repository and is used only for automated OCR regression testing.

## What the workflow does

`Camera Lab 68-Image Regression` expands `Camera Roll.zip`, verifies that all 68 source images are present, checks out the current `squish6669/RapidOCRCSharp` source, builds the Windows x64 RapidOCR benchmark, runs PP-OCRv5 across the full corpus, and scores the output against `data/Camera-Lab-Ground-Truth.csv`.

The report tracks raw exact/near serial recognition, spatial serial-extractor exact/near recognition, model recognition, OCR errors, runtime, manufacturer-level accuracy, and every remaining miss.

## Regression gate

`regression-thresholds.json` protects the proven RapidOCR baseline. A build fails if OCR errors appear or if the known 68-image baseline regresses below the stored serial/model minimums.

## Development loop

1. Patch serial/model extraction logic or RapidOCR integration.
2. Push the patch.
3. GitHub runs all 68 images automatically.
4. Review `Regression-Summary.md`, CSV, and JSON artifacts.
5. Repeat until accuracy and safety targets are reached.

The County workstation is reserved for final real-camera/WPF verification instead of being required for every development iteration.
