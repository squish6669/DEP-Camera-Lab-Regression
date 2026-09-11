# Camera Lab Operational Contract

This contract bridges validated OCR inference into the DEP Camera Lab operational workflow without introducing ground truth or speculative certificate matches.

## Production inference input

`Camera-Lab-Production-Inference.csv` is the authoritative OCR-derived input. Production inference must not consume regression ground truth. The protected 123-image workflow separately validates the output against the 68 verified rows after inference completes.

Core inference fields are `Image`, `Manufacturer`, `Serial`, `Model`, `Capacity`, field status/confidence values, and evidence/reason fields.

## Certificate lookup

Certificate data is optional and external to OCR inference. When supplied, the certificate index CSV must contain a `Serial` column and may contain `CertId` and `CertPath`.

Matching policy is intentionally strict:

- Normalize serials by uppercasing and removing non-alphanumeric separators.
- Accept only a unique exact normalized serial match.
- One exact match => `CERT_FOUND`.
- Zero exact matches with a usable inferred serial => `NO_CERT`.
- Missing inferred serial => `REVIEW`.
- Multiple exact certificate records => `REVIEW`; never silently choose one.
- No certificate index supplied => `NOT_CHECKED`.
- Fuzzy, substring, model, capacity, manufacturer, or expected-value matching is prohibited for certificate identity.

`CertMatchMethod` is populated only for accepted matches and is `EXACT_NORMALIZED_SERIAL`.

## Pending destruction

Pending-destruction assignment is an explicit downstream action; OCR never selects a bin automatically.

Assignments use a CSV with `Image`, `Serial`, and `Bin`. Allowed bins are exactly `DS-01` through `DS-12`.

An assignment is accepted only when that operational record is currently `NO_CERT`. Assigning a `CERT_FOUND`, `REVIEW`, or `NOT_CHECKED` record to destruction is rejected rather than silently accepted.

Accepted assignments produce `PendingDestructionBin` and `DestructionStatus=PENDING_DESTRUCTION`.

## Safety boundary

Regression ground truth is never a production input. Certificate matches are never fabricated. Missing or conflicting evidence routes to review instead of being guessed. The serial no-regression gate remains at 95% or higher and is evaluated separately on the verified regression subset before production inference changes are accepted.
