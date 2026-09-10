# DEP Camera Lab Regression

Regression test bench for the DEP Universal Drive Camera Lab.

The active development and release corpus is treated as **one unified 123-image corpus**. The original 68-image set remains useful only as historical regression evidence; it is no longer a separate operational batch and should not be used as the primary development denominator.

## What the workflow does

`Camera Lab Unified Corpus Regression` expands `Camera Roll.zip`, inventories the physical images, matches them to `data/Camera-Lab-Ground-Truth.csv`, runs RapidOCR across every available image, and reports whether the corpus has reached the full **123-image target**.

The workflow checks out the current `squish6669/RapidOCRCSharp` source, builds the Windows x64 RapidOCR benchmark, runs PP-OCRv5 across the corpus, and scores output against verified ground truth.

The report tracks serial recognition, model recognition, capacity extraction, OCR errors, runtime, manufacturer-level accuracy, and every remaining miss. Ground-truth fields should cover manufacturer, exact model, serial, capacity, drive type, and CT/tracking when those values are visually verifiable.

## One-command corpus recovery

Run this from the repository on the County workstation:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Build-Unified-Camera-Corpus.ps1
```

The importer:

- expands the existing `Camera Roll.zip`;
- finds the newest `Unseen-Parser-Replay*.csv` in Downloads, Desktop, or the repository;
- reads exact Camera Roll filenames and image paths from the replay;
- searches `C:\Users\<user>\OneDrive - Riverside County (RivCo.org)\Pictures\Camera Roll` recursively;
- recovers matching newer source photos;
- conservatively adds additional `WIN_20260908_*` Camera Lab source photos only until the 123-image target is reached;
- de-duplicates by filename;
- preserves all existing verified ground-truth rows;
- creates blank `Verified=NO` ground-truth rows for recovered images so no model, serial, capacity, CT, or drive type is guessed;
- produces `Unified-Corpus-Build\Camera Roll-123.zip`, a matching ground-truth CSV, and an inventory CSV.

If the workstation Camera Roll contains all source photos, the command finishes at **123 / 123**. If source files are genuinely absent, it exits incomplete and reports the exact physical count instead of fabricating records.

## Corpus policy

- Active denominator: **123 images**.
- Treat all images as one Camera Lab corpus, not separate batches.
- New drive images extend the same corpus rather than creating a new numbered batch.
- The original 68-image results are retained only as a no-regression checkpoint.
- No ground-truth value should be guessed. Unreadable fields remain blank/unverified.
- Serial behavior must not regress while model and capacity extraction are improved.

## Regression gate

`regression-thresholds.json` protects the proven recognition baseline and now defines the active promotion gate: corrected serial, selected model, and capacity accuracy must each reach **97%**. The unified workflow still reports physical corpus completeness independently from field accuracy so development can continue while recovered images are being visually verified.

## Development loop

1. Recover/maintain the full 123-image corpus and its verified ground truth.
2. Patch model/capacity/serial extraction logic or RapidOCR integration.
3. Push the patch.
4. GitHub runs the available unified corpus automatically and reports 123-image completeness.
5. Review regression, serial, model, capacity, CSV, JSON, and timing artifacts together with the single promotion-gate summary.
6. Repeat on the next code, model, or corpus change until every gated field reaches at least 97%.

The evaluation loop runs on qualifying pushes, manual dispatch, and the weekly schedule. It is not an in-run endless retry loop; each run measures the current code/model/corpus state and reports whether promotion is ready.

The County workstation is reserved for source-photo recovery plus final real-camera/WPF verification rather than being required for every development iteration.
