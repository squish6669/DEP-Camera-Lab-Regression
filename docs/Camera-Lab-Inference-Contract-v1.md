# DEP Camera Lab Production Inference Contract v1.0

This contract defines the stable boundary between the protected OCR/inference engine and downstream Camera Lab operational workflows.

## Safety invariants

- Production inference consumes OCR evidence only. Ground truth is forbidden as an inference input and may be used only afterward for validation.
- The active physical corpus remains exactly 123 images.
- Accuracy scoring remains limited to the 68 verified rows; the newer 55 images are processed but unscored until trustworthy verification is added.
- Serial identity safety is upstream of this contract and remains protected by the >=95% no-regression gate.
- Downstream consumers must treat REVIEW as unresolved evidence, never as permission to guess.

## Row identity

`Image` is the required unique record key within one inference run. Every production run must emit exactly one row per physical image.

## Required CSV columns

The v1 column order is fixed:

1. `Image`
2. `Manufacturer`
3. `ManufacturerEvidence`
4. `Serial`
5. `SerialScore`
6. `SerialStatus`
7. `SerialEvidence`
8. `SerialTopCandidates`
9. `Model`
10. `ModelStatus`
11. `ModelEvidence`
12. `Capacity`
13. `CapacityGB`
14. `CapacityConfidence`
15. `CapacityStatus`
16. `CapacityEvidence`

Any column addition, removal, rename, reorder, or semantic change requires a new contract version rather than silently changing v1.

## Status semantics

- `SerialStatus`: `FOUND` or `REVIEW`. `FOUND` requires a non-empty serial.
- `ModelStatus`: `FOUND` or `REVIEW`. `FOUND` requires a non-empty model.
- `CapacityStatus`: `READY`, `CONFIRM`, or `REVIEW`. A missing capacity must be `REVIEW`.

These statuses describe inference evidence only. They do not assert certificate state, destruction eligibility, or disposition.

## Run summary

`Camera-Lab-Production-Inference-Summary.json` must report the production row count and `ground_truth_consumed: false`.

## Operational handoff

The next stage consumes this contract to create operational records. Certificate matching is allowed only against an explicitly supplied real certificate index and currently uses unique exact normalized serial matching. Certificate states and DS-01 through DS-12 pending-destruction assignment remain downstream concerns and must never be inferred from OCR alone.

The GitHub workflow validates this contract before accuracy scoring so schema drift cannot silently reach the Camera Lab application.
